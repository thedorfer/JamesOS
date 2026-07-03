import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../models/chat_message.dart';

class ChatBubble extends StatelessWidget {
  final ChatMessage message;
  final bool showMetadata;

  const ChatBubble({super.key, required this.message, this.showMetadata = true});

  String get sourceLabel {
    if (message.sources.isEmpty) return '';

    final preferred = <String>[];
    for (final source in message.sources) {
      final label = switch (source) {
        'files' || 'file_knowledge' => 'Files',
        'memory' => 'Memory',
        'knowledge_graph' => 'Graph',
        'conversation_summaries' => 'Recall',
        'gmail' => 'Gmail',
        'calendar' => 'Calendar',
        'work' => 'Work',
        'gcu' => 'GCU',
        _ => source.replaceAll('_', ' '),
      };
      if (!preferred.contains(label)) preferred.add(label);
    }

    return preferred.take(3).join(' + ');
  }

  Color confidenceColor(BuildContext context) {
    final label = message.confidenceLabel ?? '';
    if (label.contains('High') || label.contains('🟢')) {
      return Colors.greenAccent.withValues(alpha: 0.18);
    }
    if (label.contains('Medium') || label.contains('🟡')) {
      return Colors.amberAccent.withValues(alpha: 0.16);
    }
    return Colors.redAccent.withValues(alpha: 0.16);
  }

  @override
  Widget build(BuildContext context) {
    final user = message.isUser;
    final metaLabel = sourceLabel.isNotEmpty
        ? sourceLabel
        : message.action?.replaceAll('_', ' ');

    return Align(
      alignment: user ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 760),
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: user ? Colors.blueGrey.shade700 : const Color(0xFF1E1E1F),
          borderRadius: BorderRadius.circular(20),
          border: user ? null : Border.all(color: Colors.white10),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.12),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            MarkdownBody(data: message.text),
            if (showMetadata && !user && (message.confidenceLabel != null || metaLabel != null)) ...[
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  if (message.confidenceLabel != null)
                    Chip(
                      label: Text(message.confidenceLabel!),
                      backgroundColor: confidenceColor(context),
                      side: BorderSide(color: Colors.white.withValues(alpha: 0.08)),
                    ),
                  if (metaLabel != null && metaLabel.isNotEmpty)
                    Chip(
                      label: Text(metaLabel),
                      backgroundColor: Colors.tealAccent.withValues(alpha: 0.12),
                      side: BorderSide(color: Colors.tealAccent.withValues(alpha: 0.18)),
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}
