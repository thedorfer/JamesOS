class ChatMessage {
  final String role;
  final String text;
  final String? confidenceLabel;
  final String? action;
  final List<String> sources;

  ChatMessage({
    required this.role,
    required this.text,
    this.confidenceLabel,
    this.action,
    this.sources = const [],
  });

  bool get isUser => role == 'user';
}
