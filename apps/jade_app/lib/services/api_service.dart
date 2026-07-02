import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/chat_message.dart';
import '../models/dashboard_card.dart';
import '../models/jade_settings.dart';

class ApiService {
  Future<Map<String, dynamic>> health(JadeSettings settings) async {
    final res = await http.get(Uri.parse('${settings.apiBase}/health'));
    return {'statusCode': res.statusCode, 'body': res.body};
  }

  Future<List<DashboardCard>> dashboard(JadeSettings settings, String mode) async {
    final res = await http.get(
      Uri.parse('${settings.apiBase}/dashboard?mode=$mode'),
      headers: {'X-JamesOS-Key': settings.apiKey},
    );

    final data = jsonDecode(res.body);
    final cards = data['cards'];
    if (cards is! List) return [];
    return cards
        .whereType<Map>()
        .map((item) => DashboardCard.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<ChatMessage> ask(JadeSettings settings, String question, {String mode = 'personal'}) async {
    final res = await http.post(
      Uri.parse('${settings.apiBase}/ask'),
      headers: {
        'Content-Type': 'application/json',
        'X-JamesOS-Key': settings.apiKey,
      },
      body: jsonEncode({'question': question, 'use_ai': settings.useAi, 'mode': mode}),
    );

    final data = jsonDecode(res.body);
    final planner = data['planner'];
    final reasoner = data['reasoner'];
    final reasonerSources = reasoner is Map ? reasoner['sources'] : null;
    final rawSources = reasonerSources ?? planner;
    final sources = rawSources is List
        ? rawSources.map((item) => item.toString()).toList()
        : <String>[];

    return ChatMessage(
      role: 'jade',
      text: data['answer']?.toString() ?? res.body,
      confidenceLabel: data['confidence_label']?.toString(),
      action: data['action']?.toString(),
      sources: sources,
    );
  }
}
