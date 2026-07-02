import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

void main() => runApp(const JadeApp());

class JadeApp extends StatelessWidget {
  const JadeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Jade',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark(useMaterial3: true),
      home: const ChatScreen(),
    );
  }
}

class ChatMessage {
  final String role;
  final String text;
  ChatMessage(this.role, this.text);
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final input = TextEditingController();
  final scroll = ScrollController();

  String apiBase = 'http://100.77.201.40:8787';
  String apiKey = '';
  bool loading = false;

  final messages = <ChatMessage>[
    ChatMessage('jade', 'Hi James. Jade is ready.'),
  ];

  @override
  void initState() {
    super.initState();
    loadSettings();
  }

  Future<void> loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      apiBase = prefs.getString('apiBase') ?? apiBase;
      apiKey = prefs.getString('apiKey') ?? '';
    });
  }

  Future<void> saveSettings() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('apiBase', apiBase);
    await prefs.setString('apiKey', apiKey);
  }

  Future<void> askJade() async {
    final question = input.text.trim();
    if (question.isEmpty || loading) return;

    setState(() {
      messages.add(ChatMessage('user', question));
      messages.add(ChatMessage('jade', 'Thinking...'));
      loading = true;
      input.clear();
    });

    try {
      final res = await http.post(
        Uri.parse('$apiBase/ask'),
        headers: {
          'Content-Type': 'application/json',
          'X-JamesOS-Key': apiKey,
        },
        body: jsonEncode({'question': question, 'use_ai': true}),
      );

      final data = jsonDecode(res.body);
      setState(() {
        messages[messages.length - 1] =
            ChatMessage('jade', data['answer']?.toString() ?? res.body);
      });
    } catch (e) {
      setState(() {
        messages[messages.length - 1] = ChatMessage('jade', 'Error: $e');
      });
    } finally {
      setState(() => loading = false);
    }
  }

  void openSettings() {
    final base = TextEditingController(text: apiBase);
    final key = TextEditingController(text: apiKey);

    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Jade Settings'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: base, decoration: const InputDecoration(labelText: 'API URL')),
            TextField(controller: key, obscureText: true, decoration: const InputDecoration(labelText: 'API Key')),
          ],
        ),
        actions: [
          TextButton(
            child: const Text('Save'),
            onPressed: () async {
              setState(() {
                apiBase = base.text.trim();
                apiKey = key.text.trim();
              });
              await saveSettings();
              if (mounted) Navigator.pop(context);
            },
          )
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Jade'),
        actions: [IconButton(onPressed: openSettings, icon: const Icon(Icons.settings))],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: scroll,
              padding: const EdgeInsets.all(16),
              itemCount: messages.length,
              itemBuilder: (_, i) {
                final msg = messages[i];
                final user = msg.role == 'user';
                return Align(
                  alignment: user ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    constraints: const BoxConstraints(maxWidth: 760),
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: user ? Colors.blueGrey.shade700 : Colors.grey.shade900,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: MarkdownBody(data: msg.text),
                  ),
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: input,
                    onSubmitted: (_) => askJade(),
                    decoration: const InputDecoration(
                      hintText: 'Ask Jade...',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filled(onPressed: askJade, icon: const Icon(Icons.send)),
              ],
            ),
          )
        ],
      ),
    );
  }
}
