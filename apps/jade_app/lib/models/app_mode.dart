enum AppMode {
  personal,
  work,
  gcu,
  family,
  jamesOS,
}

extension AppModeDetails on AppMode {
  String get label => switch (this) {
        AppMode.personal => 'Personal',
        AppMode.work => 'Work',
        AppMode.gcu => 'GCU',
        AppMode.family => 'Family',
        AppMode.jamesOS => 'JamesOS',
      };

  String get shortLabel => switch (this) {
        AppMode.personal => 'Personal',
        AppMode.work => 'Work',
        AppMode.gcu => 'GCU',
        AppMode.family => 'Family',
        AppMode.jamesOS => 'JamesOS',
      };

  String get directive => switch (this) {
        AppMode.personal =>
          'You are in Personal Assistant mode. Bring important things up front across James\'s life, but stay concise and practical.',
        AppMode.work =>
          'You are in Work mode. Prioritize WGL, tickets, deployments, Oracle/PLSQL work, blockers, testers, Kevin, Malcolm, Tom, Ian, and anything waiting on James.',
        AppMode.gcu =>
          'You are in GCU mode. Prioritize teaching, grading, students, announcements, assignments, due dates, and concise instructor-ready wording.',
        AppMode.family =>
          'You are in Family mode. Prioritize family logistics, schedules, reminders, school, trips, birthdays, and practical household context.',
        AppMode.jamesOS =>
          'You are in JamesOS mode. Prioritize JamesOS architecture, Flutter app work, backend status, Git, deploys, services, memory, knowledge graph, and next coding steps.',
      };

  String get briefingPrompt => switch (this) {
        AppMode.personal =>
          'Jade, give me a prioritized briefing for right now. Bring the important things up front across work, GCU, family, JamesOS, calendar, and recent memory. Keep it concise and action-oriented.',
        AppMode.work =>
          'Jade, bring forward the most important work items I should focus on right now. Prioritize WGL tickets, blockers, Kevin/Malcolm/Tom context, deployments, and anything waiting on me.',
        AppMode.gcu =>
          'Jade, bring forward the most important GCU teaching items I should focus on right now. Prioritize grading, students, announcements, and upcoming course work.',
        AppMode.family =>
          'Jade, bring forward important family or personal items I should keep in mind right now. Be practical and concise.',
        AppMode.jamesOS =>
          'Jade, bring forward the most important JamesOS development items. Prioritize broken builds, deploy status, next coding tasks, and architecture decisions.',
      };
}
