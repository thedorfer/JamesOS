import 'package:flutter/material.dart';
import '../models/chat_message.dart';
import '../models/jade_settings.dart';
import '../services/api_service.dart';
import '../services/settings_service.dart';
import '../widgets/chat_bubble.dart';
import '../widgets/message_input.dart';
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
  String selectedMode = 'Personal';

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

  Future<void> openSettings() async {
    final updated = await Navigator.push<JadeSettings>(
      context,
      MaterialPageRoute(builder: (_) => SettingsScreen(settings: settings)),
    );

    if (updated != null) {
      setState(() => settings = updated);
      await refreshStatus();
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
      final response = await api.ask(settings, question);
      setState(() => messages[messages.length - 1] = response);
      await refreshStatus();
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

  void runMode(String mode) {
    setState(() => selectedMode = mode);

    final prompt = switch (mode) {
      'Work' => 'Jade, bring forward the most important work items I should focus on right now. Prioritize WGL tickets, blockers, Kevin/Malcolm/Tom context, deployments, and anything waiting on me.',
      'GCU' => 'Jade, bring forward the most important GCU teaching items I should focus on right now. Prioritize grading, students, announcements, and upcoming course work.',
      'Family' => 'Jade, bring forward important family or personal items I should keep in mind right now. Be practical and concise.',
      'JamesOS' => 'Jade, bring forward the most important JamesOS development items. Prioritize broken builds, deploy status, next coding tasks, and architecture decisions.',
      _ => 'Jade, give me a focused personal assistant briefing for right now. Bring important things up front and skip filler.',
    };

    askJade(overrideQuestion: prompt);
  }

  Widget buildStatusRow() {
    return Row(
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(
            color: serverOnline ? Colors.greenAccent : Colors.redAccent,
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: 8),
        Text(
          serverOnline ? 'JamesOS online' : 'JamesOS offline',
          style: TextStyle(
            fontWeight: FontWeight.w700,
            color: serverOnline ? Colors.greenAccent.shade100 : Colors.redAccent.shade100,
          ),
        ),
        const Spacer(),
        TextButton.icon(
          onPressed: refreshStatus,
          icon: const Icon(Icons.refresh, size: 18),
          label: const Text('Refresh'),
        ),
      ],
    );
  }

  Widget modeChip(String mode, IconData icon) {
    final selected = selectedMode == mode;
    return ChoiceChip(
      selected: selected,
      avatar: Icon(icon, size: 18),
      label: Text(mode),
      onSelected: (_) => runMode(mode),
      selectedColor: Colors.tealAccent.withValues(alpha: 0.22),
      backgroundColor: Colors.white.withValues(alpha: 0.045),
      side: BorderSide(
        color: selected
            ? Colors.tealAccent.withValues(alpha: 0.48)
            : Colors.white.withValues(alpha: 0.12),
      ),
    );
  }

  Widget buildDashboardCard() {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.teal.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.tealAccent.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Good afternoon, James',
            style: TextStyle(fontSize: 23, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 10),
          buildStatusRow(),
          const SizedBox(height: 12),
          const Text(
            'Important things first. Choose a mode and Jade will pull the right context forward.',
            style: TextStyle(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              modeChip('Work', Icons.work_outline),
              modeChip('GCU', Icons.school_outlined),
              modeChip('Family', Icons.home_outlined),
              modeChip('JamesOS', Icons.memory_outlined),
              modeChip('Personal', Icons.auto_awesome_outlined),
            ],
          ),
          const SizedBox(height: 14),
          FilledButton.icon(
            onPressed: loading
                ? null
                : () => askJade(
                      overrideQuestion:
                          'Jade, give me a prioritized briefing for right now. Bring the important things up front across work, GCU, family, JamesOS, calendar, and recent memory. Keep it concise and action-oriented.',
                    ),
            icon: const Icon(Icons.flash_on),
            label: const Text('Brief me'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final paired = settings.apiKey.isNotEmpty;

    return Scaffold(
      appBar: AppBar(
        title: Text(settings.assistantName),
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
