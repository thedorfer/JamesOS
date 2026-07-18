class DashboardCard {
  final String title;
  final String body;
  final String kind;
  final String prompt;

  DashboardCard({
    required this.title,
    required this.body,
    required this.kind,
    required this.prompt,
  });

  factory DashboardCard.fromJson(Map<String, dynamic> json) {
    return DashboardCard(
      title: json['title']?.toString() ?? 'Item',
      body: json['body']?.toString() ?? '',
      kind: json['kind']?.toString() ?? 'info',
      prompt:
          json['prompt']?.toString() ?? json['title']?.toString() ?? 'Brief me',
    );
  }
}
