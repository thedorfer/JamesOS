class JadeSettings {
  String apiBase;
  String apiKey;
  String assistantName;
  bool useAi;
  bool voiceReplies;

  JadeSettings({
    this.apiBase = 'http://100.77.201.40:8787',
    this.apiKey = '',
    this.assistantName = 'Jade',
    this.useAi = true,
    this.voiceReplies = false,
  });
}
