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

  Future<Map<String, dynamic>> uploadAttachment(
    JadeSettings settings,
    String filename,
    List<int> bytes,
  ) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('${settings.apiBase}/attachments/ingest'),
    );

    request.headers['X-JamesOS-Key'] = settings.apiKey;
    request.files.add(http.MultipartFile.fromBytes('files', bytes, filename: filename));

    final streamed = await request.send();
    final body = await streamed.stream.bytesToString();

    if (streamed.statusCode < 200 || streamed.statusCode >= 300) {
      throw Exception('Upload failed: ${streamed.statusCode} $body');
    }

    if (body.trim().isEmpty) {
      return {'status': 'ok'};
    }

    final decoded = jsonDecode(body);
    if (decoded is Map<String, dynamic>) return decoded;
    return {'status': 'ok', 'result': decoded};
  }

  Future<Map<String, dynamic>> processAttachments(JadeSettings settings) async {
    final res = await http.post(
      Uri.parse('${settings.apiBase}/attachments/process-pending?limit=10'),
      headers: {'X-JamesOS-Key': settings.apiKey},
    );

    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('Processing failed: ${res.statusCode} ${res.body}');
    }

    final decoded = jsonDecode(res.body);
    if (decoded is Map<String, dynamic>) return decoded;
    return {'status': 'ok', 'result': decoded};
  }

  String uploadMessage(Map<String, dynamic> uploadResult, String fallbackFilename) {
    final message = uploadResult['message'];
    if (message is String && message.trim().isNotEmpty) return message;

    final files = uploadResult['files'];
    if (files is List && files.isNotEmpty && files.first is Map) {
      final first = Map<String, dynamic>.from(files.first as Map);
      final summary = first['summary'];
      if (summary is String && summary.trim().isNotEmpty) return summary;
      final kind = first['kind']?.toString() ?? 'file';
      final filename = first['filename']?.toString() ?? fallbackFilename;
      return 'I received `$filename` as a $kind and queued it for processing.';
    }

    return 'I received `$fallbackFilename` and queued it for processing.';
  }
}
