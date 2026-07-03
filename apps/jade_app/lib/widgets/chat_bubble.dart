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
        'knowledge_graph' => 'Knowledge',
        'conversation_summaries' => 'Recall',
        'gmail' => 'Gmail',
        'calendar' => 'Calendar',
        'work' => 'Work',
        'gcu' => 'GCU',
        _ => source.replaceAll('_', ' '),
      };
      if (!preferred.contains(label)) preferred.add(label);
    }

    return preferred.take(4).join(' • ');
  }

  bool get hasLowConfidence {
    final label = message.confidenceLabel ?? '';
    return label.contains('Low') || label.contains('🔴');
  }

  bool get hasLimitedConfidence {
    final label = message.confidenceLabel ?? '';
    return label.contains('Medium') || label.contains('🟡') || hasLowConfidence;
  }

  @override
  Widget build(BuildContext context) {
    final user = message.isUser;
    final metaLabel = sourceLabel.isNotEmpty
        ? 'Based on $sourceLabel'
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
            if (showMetadata && !user && metaLabel != null && metaLabel.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(
                hasLimitedConfidence ? '$metaLabel. Some details may need verification.' : metaLabel,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.55),
                  fontSize: 12,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
