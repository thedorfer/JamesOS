import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/chat_message.dart';
import '../models/jade_settings.dart';

class ApiService {
  Future<Map<String, dynamic>> health(JadeSettings settings) async {
    final res = await http.get(Uri.parse('${settings.apiBase}/health'));
    return {'statusCode': res.statusCode, 'body': res.body};
  }

  Future<ChatMessage> ask(JadeSettings settings, String question) async {
    final res = await http.post(
      Uri.parse('${settings.apiBase}/ask'),
      headers: {
        'Content-Type': 'application/json',
        'X-JamesOS-Key': settings.apiKey,
      },
      body: jsonEncode({'question': question, 'use_ai': settings.useAi}),
    );

    final data = jsonDecode(res.body);
    return ChatMessage(
      role: 'jade',
      text: data['answer']?.toString() ?? res.body,
      confidenceLabel: data['confidence_label']?.toString(),
      action: data['action']?.toString(),
    );
  }
}
