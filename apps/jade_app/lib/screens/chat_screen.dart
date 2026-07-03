import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import '../models/app_mode.dart';
import '../models/chat_message.dart';
import '../models/dashboard_card.dart';
import '../models/jade_settings.dart';
import '../services/api_service.dart';
import '../services/settings_service.dart';
import '../widgets/chat_bubble.dart';
import '../widgets/message_input.dart';
import '../widgets/status_chip.dart';
import 'settings_screen.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final input = TextEditingController();
  final scroll = ScrollController();
  final api = ApiService();
  final tts = FlutterTts();
  final recognizer = stt.SpeechToText();

  JadeSettings settings = JadeSettings();
  bool loading = false;
  bool serverOnline = false;
  bool speaking = false;
  bool listening = false;
  bool speechAvailable = false;
  bool voiceAutoSubmitted = false;
  AppMode selectedMode = AppMode.personal;
  List<DashboardCard> dashboardCards = [];

  final messages = <ChatMessage>[ChatMessage(role: 'jade', text: 'Hi James. Jade is ready.')];

  @override
  void initState() {
    super.initState();
    configureVoice();
    configureSpeechInput();
    loadSettings();
  }

  @override
  void dispose() {
    input.dispose();
    scroll.dispose();
    tts.stop();
    recognizer.stop();
    super.dispose();
  }

  Future<void> configureVoice() async {
    await tts.setLanguage('en-US');
    await tts.setSpeechRate(0.46);
    await tts.setPitch(1.03);
    await tts.awaitSpeakCompletion(false);
    tts.setStartHandler(() { if (mounted) setState(() => speaking = true); });
    tts.setCompletionHandler(() { if (mounted) setState(() => speaking = false); });
    tts.setCancelHandler(() { if (mounted) setState(() => speaking = false); });
    tts.setErrorHandler((_) { if (mounted) setState(() => speaking = false); });
  }

  Future<void> configureSpeechInput() async {
    final ok = await recognizer.initialize(
      onStatus: (status) {
        if (!mounted) return;
        final active = status == 'listening';
        if (listening != active) setState(() => listening = active);

        if ((status == 'done' || status == 'notListening') &&
            input.text.trim().isNotEmpty &&
            !loading &&
            !voiceAutoSubmitted) {
          voiceAutoSubmitted = true;
          Future.delayed(const Duration(milliseconds: 250), () {
            if (mounted && input.text.trim().isNotEmpty && !loading) {
              askJade();
            }
          });
        }
      },
      onError: (_) { if (mounted) setState(() => listening = false); },
    );
    if (mounted) setState(() => speechAvailable = ok);
  }

  String speechText(String text) => text
      .replaceAll(RegExp(r'`([^`]*)`'), r'$1')
      .replaceAll(RegExp(r'\*'), '')
      .replaceAll(RegExp(r'#+\s*'), '')
      .replaceAll(RegExp(r'\[[^\]]*\]\([^\)]*\)'), '')
      .replaceAll(RegExp(r'[🟢🟡🔴⚪✨⚡]'), '')
      .replaceAll(RegExp(r'\n{2,}'), '. ')
      .replaceAll('\n', '. ')
      .trim();

  bool shouldAutoSpeak(String text) => settings.voiceReplies && selectedMode.isChatty && speechText(text).length <= 450;

  Future<void> speak(String text, {bool force = false}) async {
    if (!force && !shouldAutoSpeak(text)) return;
    final cleaned = speechText(text);
    if (cleaned.isEmpty) return;
    await tts.stop();
    await tts.speak(cleaned);
  }

  Future<void> toggleSpeech() async {
    if (speaking) {
      await tts.stop();
      setState(() => speaking = false);
      return;
    }
    final lastJade = messages.reversed.where((m) => !m.isUser).firstOrNull;
    if (lastJade != null) await speak(lastJade.text, force: true);
  }

  Future<void> toggleListening() async {
    if (listening) {
      await recognizer.stop();
      if (mounted) setState(() => listening = false);
      return;
    }
    if (!speechAvailable) await configureSpeechInput();
    if (!speechAvailable) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Speech input is not available.')));
      return;
    }
    await tts.stop();
    if (mounted) setState(() => speaking = false);
    voiceAutoSubmitted = false;
    await recognizer.listen(
      listenMode: stt.ListenMode.confirmation,
      partialResults: true,
      onResult: (result) {
        input.text = result.recognizedWords;
        input.selection = TextSelection.fromPosition(TextPosition(offset: input.text.length));
      },
    );
    if (mounted) setState(() => listening = true);
  }

  void showFileInputSoon() {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('File input is next. Speech input is enabled now.')));
  }

  Future<void> loadSettings() async {
    final loaded = await SettingsService().load();
    if (!mounted) return;
    setState(() => settings = loaded);
    await refreshStatus();
    await refreshDashboard();
  }

  Future<void> refreshStatus() async {
    try {
      final res = await api.health(settings);
      if (mounted) setState(() => serverOnline = res['statusCode'] == 200);
    } catch (_) {
      if (mounted) setState(() => serverOnline = false);
    }
  }

  Future<void> refreshDashboard() async {
    if (settings.apiKey.isEmpty) return;
    try {
      final cards = await api.dashboard(settings, selectedMode.key);
      if (mounted) setState(() => dashboardCards = cards);
    } catch (_) {
      if (mounted) setState(() => dashboardCards = []);
    }
  }

  Future<void> openSettings() async {
    final updated = await Navigator.push<JadeSettings>(context, MaterialPageRoute(builder: (_) => SettingsScreen(settings: settings)));
    if (updated != null) {
      setState(() => settings = updated);
      await refreshStatus();
      await refreshDashboard();
    }
  }

  Future<void> askJade({String? overrideQuestion, bool showUserMessage = true}) async {
    final question = (overrideQuestion ?? input.text).trim();
    if (question.isEmpty || loading) return;
    await recognizer.stop();
    setState(() {
      listening = false;
      if (showUserMessage) {
        messages.add(ChatMessage(role: 'user', text: question));
      }
      messages.add(ChatMessage(role: 'jade', text: 'Thinking...'));
      loading = true;
      input.clear();
    });
    scrollToBottom();
    try {
      final response = await api.ask(settings, question, mode: selectedMode.key);
      setState(() => messages[messages.length - 1] = response);
      await speak(response.text);
      await refreshStatus();
      await refreshDashboard();
    } catch (e) {
      final error = ChatMessage(role: 'jade', text: 'I could not reach JamesOS.\n\n`$e`', confidenceLabel: '🔴 Low', action: 'connection_error');
      setState(() {
        serverOnline = false;
        messages[messages.length - 1] = error;
      });
      await speak(error.text);
    } finally {
      setState(() => loading = false);
      Future.delayed(const Duration(milliseconds: 100), scrollToBottom);
    }
  }

  void scrollToBottom() {
    if (!scroll.hasClients) return;
    scroll.animateTo(scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
  }

  void clearChat() {
    tts.stop();
    recognizer.stop();
    setState(() {
      speaking = false;
      listening = false;
      messages.clear();
      messages.add(ChatMessage(role: 'jade', text: 'Fresh chat. I am ready.'));
    });
  }

  Future<void> changeMode(AppMode? mode) async {
    if (mode == null || mode == selectedMode) return;
    await tts.stop();
    await recognizer.stop();
    setState(() {
      selectedMode = mode;
      speaking = false;
      listening = false;
    });
    await refreshDashboard();
  }

  IconData modeIcon(AppMode mode) => switch (mode) {
        AppMode.chat => Icons.casino_outlined,
        AppMode.work => Icons.work_outline,
        AppMode.gcu => Icons.school_outlined,
        AppMode.family => Icons.home_outlined,
        AppMode.jamesOS => Icons.memory_outlined,
        AppMode.personal => Icons.auto_awesome_outlined,
      };

  Widget buildModeDropdown() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.045),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.tealAccent.withValues(alpha: 0.22)),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<AppMode>(
          value: selectedMode,
          borderRadius: BorderRadius.circular(18),
          icon: const Icon(Icons.keyboard_arrow_down),
          items: AppMode.values.map((mode) => DropdownMenuItem(value: mode, child: Row(mainAxisSize: MainAxisSize.min, children: [Icon(modeIcon(mode), size: 18, color: Colors.tealAccent.shade100), const SizedBox(width: 8), Text(mode.label)]))).toList(),
          onChanged: changeMode,
        ),
      ),
    );
  }

  Widget buildLiveCard(DashboardCard card) {
    final icon = switch (card.kind) {
      'world' => Icons.verified_outlined,
      'memory' => Icons.history,
      'report' => Icons.article_outlined,
      'action' => Icons.flash_on,
      'mode' => Icons.tune,
      _ => Icons.auto_awesome,
    };
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: () => askJade(overrideQuestion: card.prompt, showUserMessage: false),
      child: Container(
        width: 245,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(color: Colors.grey.shade900, borderRadius: BorderRadius.circular(16), border: Border.all(color: Colors.white.withValues(alpha: 0.08))),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [Icon(icon, size: 18, color: Colors.tealAccent.shade100), const SizedBox(width: 8), Expanded(child: Text(card.title, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800)))]),
          const SizedBox(height: 8),
          Text(card.body, maxLines: 3, overflow: TextOverflow.ellipsis, style: TextStyle(color: Colors.white.withValues(alpha: 0.76), fontSize: 12.5)),
        ]),
      ),
    );
  }

  Widget buildDashboardCard() {
    final buttonLabel = selectedMode.isChatty ? 'Surprise me' : 'Brief me';
    final voiceTooltip = speaking ? 'Stop voice' : 'Replay last response';
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: Colors.teal.withValues(alpha: 0.10), borderRadius: BorderRadius.circular(22), border: Border.all(color: Colors.tealAccent.withValues(alpha: 0.22))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Expanded(child: Text('Good afternoon, James', style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold))),
          IconButton(tooltip: voiceTooltip, onPressed: settings.voiceReplies ? toggleSpeech : null, icon: Icon(speaking ? Icons.stop_circle_outlined : Icons.volume_up_outlined)),
          IconButton(tooltip: 'Refresh live cards', onPressed: refreshDashboard, icon: const Icon(Icons.refresh)),
        ]),
        const SizedBox(height: 10),
        Row(children: [
          buildModeDropdown(),
          const Spacer(),
          FilledButton.icon(onPressed: loading ? null : () => askJade(overrideQuestion: selectedMode.briefingPrompt, showUserMessage: false), icon: Icon(selectedMode.isChatty ? Icons.casino_outlined : Icons.flash_on, size: 18), label: Text(buttonLabel)),
        ]),
        if (dashboardCards.isNotEmpty) ...[
          const SizedBox(height: 14),
          const Text('Live cards', style: TextStyle(fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          SizedBox(height: 125, child: ListView.separated(scrollDirection: Axis.horizontal, itemCount: dashboardCards.length, separatorBuilder: (_, separatorIndex) => const SizedBox(width: 10), itemBuilder: (_, i) => buildLiveCard(dashboardCards[i]))),
        ],
      ]),
    );
  }

  Widget buildTopBarTitle() {
    return Row(children: [Text(settings.assistantName), const SizedBox(width: 10), Flexible(child: StatusChip(online: serverOnline, label: 'OS', onTap: refreshStatus))]);
  }

  @override
  Widget build(BuildContext context) {
    final paired = settings.apiKey.isNotEmpty;
    return Scaffold(
      appBar: AppBar(title: buildTopBarTitle(), actions: [IconButton(onPressed: clearChat, icon: const Icon(Icons.delete_outline)), IconButton(onPressed: openSettings, icon: const Icon(Icons.settings))]),
      body: Column(children: [
        if (!paired) Container(width: double.infinity, padding: const EdgeInsets.all(12), color: Colors.amber.withValues(alpha: 0.18), child: const Text('Add your JamesOS API key in Settings.')),
        Expanded(child: ListView.builder(controller: scroll, padding: const EdgeInsets.all(16), itemCount: messages.length + 1, itemBuilder: (_, i) { if (i == 0) return buildDashboardCard(); return ChatBubble(message: messages[i - 1], showMetadata: !selectedMode.isChatty); })),
        MessageInput(controller: input, loading: loading, listening: listening, speechAvailable: speechAvailable, onSend: askJade, onVoice: toggleListening, onAttach: showFileInputSoon),
      ]),
    );
  }
}
