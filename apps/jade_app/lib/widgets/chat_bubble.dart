import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../models/chat_message.dart';

class ChatBubble extends StatelessWidget {
  final ChatMessage message;

  const ChatBubble({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    final user = message.isUser;

    return Align(
      alignment: user ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 760),
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: user ? Colors.blueGrey.shade700 : Colors.grey.shade900,
          borderRadius: BorderRadius.circular(18),
          border: user ? null : Border.all(color: Colors.white10),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            MarkdownBody(data: message.text),
            if (!user && (message.confidenceLabel != null || message.action != null)) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  if (message.confidenceLabel != null)
                    Chip(label: Text(message.confidenceLabel!)),
                  if (message.action != null) Chip(label: Text(message.action!)),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}
