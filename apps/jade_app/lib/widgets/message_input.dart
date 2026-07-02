import 'package:flutter/material.dart';

class MessageInput extends StatelessWidget {
  final TextEditingController controller;
  final bool loading;
  final VoidCallback onSend;

  const MessageInput({
    super.key,
    required this.controller,
    required this.loading,
    required this.onSend,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            IconButton(onPressed: null, icon: const Icon(Icons.attach_file)),
            IconButton(onPressed: null, icon: const Icon(Icons.mic)),
            Expanded(
              child: TextField(
                controller: controller,
                onSubmitted: (_) => onSend(),
                minLines: 1,
                maxLines: 4,
                decoration: const InputDecoration(
                  hintText: 'Ask Jade...',
                  border: OutlineInputBorder(),
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              onPressed: loading ? null : onSend,
              icon: loading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.send),
            ),
          ],
        ),
      ),
    );
  }
}
