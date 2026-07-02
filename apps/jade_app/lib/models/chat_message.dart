class ChatMessage {
  final String role;
  final String text;
  final String? confidenceLabel;
  final String? action;

  ChatMessage({
    required this.role,
    required this.text,
    this.confidenceLabel,
    this.action,
  });

  bool get isUser => role == 'user';
}
