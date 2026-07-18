import 'package:flutter/material.dart';

class MessageInput extends StatelessWidget {
  final TextEditingController controller;
  final bool loading;
  final bool listening;
  final bool speechAvailable;
  final VoidCallback onSend;
  final VoidCallback onVoice;
  final VoidCallback? onAttach;

  const MessageInput({
    super.key,
    required this.controller,
    required this.loading,
    required this.onSend,
    required this.onVoice,
    this.listening = false,
    this.speechAvailable = true,
    this.onAttach,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
        decoration: BoxDecoration(
          color: Theme.of(
            context,
          ).scaffoldBackgroundColor.withValues(alpha: 0.96),
          border: Border(
            top: BorderSide(color: Colors.white.withValues(alpha: 0.06)),
          ),
        ),
        child: Row(
          children: [
            IconButton(
              tooltip: 'Attach file',
              onPressed: onAttach,
              icon: const Icon(Icons.attach_file),
            ),
            IconButton(
              tooltip: listening ? 'Stop listening' : 'Voice input',
              onPressed: loading || !speechAvailable ? null : onVoice,
              color: listening ? Colors.tealAccent.shade100 : null,
              icon: Icon(listening ? Icons.mic_off : Icons.mic),
            ),
            Expanded(
              child: TextField(
                controller: controller,
                onSubmitted: (_) => onSend(),
                minLines: 1,
                maxLines: 4,
                decoration: InputDecoration(
                  hintText: listening ? 'Listening...' : 'Ask Jade...',
                  filled: true,
                  fillColor: Colors.white.withValues(alpha: 0.045),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 14,
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(16),
                    borderSide: BorderSide(
                      color: Colors.white.withValues(alpha: 0.12),
                    ),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(16),
                    borderSide: const BorderSide(
                      color: Colors.tealAccent,
                      width: 1.6,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 10),
            SizedBox(
              height: 54,
              width: 54,
              child: IconButton.filled(
                onPressed: loading ? null : onSend,
                style: IconButton.styleFrom(
                  backgroundColor: Colors.tealAccent.shade100,
                  foregroundColor: Colors.black87,
                ),
                icon: loading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.send_rounded, size: 28),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
