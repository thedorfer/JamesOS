import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jade_app/models/jade_settings.dart';
import 'package:jade_app/screens/agency_screen.dart';

void main() {
  final catalog = <Map<String, dynamic>>[
    {
      'agent': {
        'name': 'Example Agent',
        'publisher': 'JamesOS',
        'version': '0.1.0',
        'description': 'Safe local example',
      },
      'category': 'HomeOps',
      'tags': ['local'],
      'installed': false,
      'status': 'available',
      'configuration': [
        {'name': 'limit', 'label': 'Limit', 'type': 'integer', 'default': 5},
        {
          'name': 'enabled',
          'label': 'Enabled',
          'type': 'boolean',
          'default': false,
        },
      ],
    },
  ];

  testWidgets('Agency discovers agents and renders manifest configuration', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1100, 750));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        home: AgencyScreen(settings: JadeSettings(), catalogOverride: catalog),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('The Agency'), findsOneWidget);
    expect(find.text('Example Agent'), findsOneWidget);
    await expectLater(
      find.byType(AgencyScreen),
      matchesGoldenFile('goldens/the_agency_discover.png'),
    );
    await tester.tap(find.text('Example Agent'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Configuration'));
    await tester.pumpAndSettle();
    expect(find.text('Limit'), findsOneWidget);
    expect(find.text('Enabled'), findsOneWidget);
    await expectLater(
      find.byType(AgentManagementScreen),
      matchesGoldenFile('goldens/the_agency_configuration.png'),
    );
  });
}
