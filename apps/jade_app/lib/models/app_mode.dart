enum AppMode {
  personal,
  chat,
  work,
  gcu,
  family,
  jamesOS,
}

extension AppModeDetails on AppMode {
  String get key => switch (this) {
        AppMode.personal => 'personal',
        AppMode.chat => 'chat',
        AppMode.work => 'work',
        AppMode.gcu => 'gcu',
        AppMode.family => 'family',
        AppMode.jamesOS => 'jamesos',
      };

  String get label => switch (this) {
        AppMode.personal => 'Personal',
        AppMode.chat => 'Chat',
        AppMode.work => 'Work',
        AppMode.gcu => 'GCU',
        AppMode.family => 'Family',
        AppMode.jamesOS => 'JamesOS',
      };

  String get shortLabel => label;

  bool get isChatty => this == AppMode.chat;

  String get briefingPrompt => switch (this) {
        AppMode.personal =>
          'Give me a prioritized briefing for right now across work, GCU, family, JamesOS, calendar, and recent memory. Keep it concise and action-oriented.',
        AppMode.chat =>
          'Say something light, funny, or interesting. Keep it short and conversational.',
        AppMode.work =>
          'Bring forward the most important work items I should focus on right now. Prioritize WGL tickets, blockers, Kevin/Malcolm/Tom context, deployments, and anything waiting on me.',
        AppMode.gcu =>
          'Bring forward the most important GCU teaching items I should focus on right now. Prioritize grading, students, announcements, and upcoming course work.',
        AppMode.family =>
          'Bring forward important family or personal items I should keep in mind right now. Be practical and concise.',
        AppMode.jamesOS =>
          'Bring forward the most important JamesOS development items. Prioritize broken builds, deploy status, next coding tasks, and architecture decisions.',
      };
}
