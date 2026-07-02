import 'package:flutter/material.dart';
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

  JadeSettings settings = JadeSettings();
  bool loading = false;
  bool serverOnline = false;
  AppMode selectedMode = AppMode.personal;
  List<DashboardCard> dashboardCards = [];

  final messages = <ChatMessage>[
    ChatMessage(role: 'jade', text: 'Hi James. Jade is ready.'),
  ];

  @override
  void initState() {
    super.initState();
    loadSettings();
  }

  @override
  void dispose() {
    input.dispose();
    scroll.dispose();
    super.dispose();
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
      if (!mounted) return;
      setState(() => serverOnline = res['statusCode'] == 200);
    } catch (_) {
      if (!mounted) return;
      setState(() => serverOnline = false);
    }
  }

  Future<void> refreshDashboard() async {
    if (settings.apiKey.isEmpty) return;
    try {
      final cards = await api.dashboard(settings, selectedMode.key);
      if (!mounted) return;
      setState(() => dashboardCards = cards);
    } catch (_) {
      if (!mounted) return;
      setState(() => dashboardCards = []);
    }
  }

  Future<void> openSettings() async {
    final updated = await Navigator.push<JadeSettings>(
      context,
      MaterialPageRoute(builder: (_) => SettingsScreen(settings: settings)),
    );

    if (updated != null) {
      setState(() => settings = updated);
      await refreshStatus();
      await refreshDashboard();
    }
  }

  Future<void> askJade({String? overrideQuestion}) async {
    final question = (overrideQuestion ?? input.text).trim();
    if (question.isEmpty || loading) return;

    setState(() {
      messages.add(ChatMessage(role: 'user', text: question));
      messages.add(ChatMessage(role: 'jade', text: 'Thinking...'));
      loading = true;
      input.clear();
    });

    scrollToBottom();

    try {
      final response = await api.ask(settings, question, mode: selectedMode.key);
      setState(() => messages[messages.length - 1] = response);
      await refreshStatus();
      await refreshDashboard();
    } catch (e) {
      setState(() {
        serverOnline = false;
        messages[messages.length - 1] = ChatMessage(
          role: 'jade',
          text: 'I could not reach JamesOS.\n\n`$e`',
          confidenceLabel: '🔴 Low',
          action: 'connection_error',
        );
      });
    } finally {
      setState(() => loading = false);
      Future.delayed(const Duration(milliseconds: 100), scrollToBottom);
    }
  }

  void scrollToBottom() {
    if (!scroll.hasClients) return;
    scroll.animateTo(
      scroll.position.maxScrollExtent,
      duration: const Duration(milliseconds: 250),
      curve: Curves.easeOut,
    );
  }

  void clearChat() {
    setState(() {
      messages.clear();
      messages.add(ChatMessage(role: 'jade', text: 'Fresh chat. I am ready.'));
    });
  }

  Future<void> changeMode(AppMode? mode) async {
    if (mode == null || mode == selectedMode) return;
    setState(() => selectedMode = mode);
    await refreshDashboard();
  }

  IconData modeIcon(AppMode mode) => switch (mode) {
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
          items: AppMode.values
              .map(
                (mode) => DropdownMenuItem(
                  value: mode,
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(modeIcon(mode), size: 18, color: Colors.tealAccent.shade100),
                      const SizedBox(width: 8),
                      Text(mode.label),
                    ],
                  ),
                ),
              )
              .toList(),
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
      onTap: () => askJade(overrideQuestion: card.prompt),
      child: Container(
        width: 245,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 18, color: Colors.tealAccent.shade100),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    card.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              card.body,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(color: Colors.white.withValues(alpha: 0.76), fontSize: 12.5),
            ),
          ],
        ),
      ),
    );
  }

  Widget buildDashboardCard() {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.teal.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: Colors.tealAccent.withValues(alpha: 0.22)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  'Good afternoon, James',
                  style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                ),
              ),
              IconButton(
                tooltip: 'Refresh live cards',
                onPressed: refreshDashboard,
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              buildModeDropdown(),
              const Spacer(),
              FilledButton.icon(
                onPressed: loading ? null : () => askJade(overrideQuestion: selectedMode.briefingPrompt),
                icon: const Icon(Icons.flash_on, size: 18),
                label: const Text('Brief me'),
              ),
            ],
          ),
          if (dashboardCards.isNotEmpty) ...[
            const SizedBox(height: 14),
            const Text('Live cards', style: TextStyle(fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            SizedBox(
              height: 125,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: dashboardCards.length,
                separatorBuilder: (_, separatorIndex) => const SizedBox(width: 10),
                itemBuilder: (_, i) => buildLiveCard(dashboardCards[i]),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget buildTopBarTitle() {
    return Row(
      children: [
        Text(settings.assistantName),
        const SizedBox(width: 10),
        Flexible(child: StatusChip(online: serverOnline, label: 'OS', onTap: refreshStatus)),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final paired = settings.apiKey.isNotEmpty;

    return Scaffold(
      appBar: AppBar(
        title: buildTopBarTitle(),
        actions: [
          IconButton(onPressed: clearChat, icon: const Icon(Icons.delete_outline)),
          IconButton(onPressed: openSettings, icon: const Icon(Icons.settings)),
        ],
      ),
      body: Column(
        children: [
          if (!paired)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              color: Colors.amber.withValues(alpha: 0.18),
              child: const Text('Add your JamesOS API key in Settings.'),
            ),
          Expanded(
            child: ListView.builder(
              controller: scroll,
              padding: const EdgeInsets.all(16),
              itemCount: messages.length + 1,
              itemBuilder: (_, i) {
                if (i == 0) return buildDashboardCard();
                return ChatBubble(message: messages[i - 1]);
              },
            ),
          ),
          MessageInput(controller: input, loading: loading, onSend: askJade),
        ],
      ),
    );
  }
}
