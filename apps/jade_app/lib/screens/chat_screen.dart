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
  }

  Future<void> openSettings() async {
    final updated = await Navigator.push<JadeSettings>(
      context,
      MaterialPageRoute(builder: (_) => SettingsScreen(settings: settings)),
    );

    if (updated != null) {
      setState(() => settings = updated);
    }
  }

  Future<void> askJade() async {
    final question = input.text.trim();
    if (question.isEmpty || loading) return;

    setState(() {
      messages.add(ChatMessage(role: 'user', text: question));
      messages.add(ChatMessage(role: 'jade', text: 'Thinking...'));
      loading = true;
      input.clear();
    });

    try {
      final response = await api.ask(settings, question);
      setState(() => messages[messages.length - 1] = response);
    } catch (e) {
      setState(() {
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

  Widget buildHomeCard() {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.teal.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: Colors.tealAccent.withValues(alpha: 0.25)),
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Good afternoon, James',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
          SizedBox(height: 8),
          Text('Jade is connected to JamesOS. What are we working on?'),
          SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              Chip(label: Text('Work')),
              Chip(label: Text('GCU')),
              Chip(label: Text('Family')),
              Chip(label: Text('JamesOS')),
            ],
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
                if (i == 0) return buildHomeCard();
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
