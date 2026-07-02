import 'package:shared_preferences/shared_preferences.dart';
import '../models/jade_settings.dart';

class SettingsService {
  Future<JadeSettings> load() async {
    final prefs = await SharedPreferences.getInstance();
    return JadeSettings(
      apiBase: prefs.getString('apiBase') ?? 'http://100.77.201.40:8787',
      apiKey: prefs.getString('apiKey') ?? '',
      assistantName: prefs.getString('assistantName') ?? 'Jade',
      useAi: prefs.getBool('useAi') ?? true,
      voiceReplies: prefs.getBool('voiceReplies') ?? false,
    );
  }

  Future<void> save(JadeSettings settings) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('apiBase', settings.apiBase);
    await prefs.setString('apiKey', settings.apiKey);
    await prefs.setString('assistantName', settings.assistantName);
    await prefs.setBool('useAi', settings.useAi);
    await prefs.setBool('voiceReplies', settings.voiceReplies);
  }
}
