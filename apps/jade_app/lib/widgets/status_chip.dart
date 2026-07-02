import 'package:flutter/material.dart';

class StatusChip extends StatelessWidget {
  final bool online;
  final String label;
  final VoidCallback? onTap;

  const StatusChip({
    super.key,
    required this.online,
    this.label = 'JamesOS',
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final color = online ? Colors.greenAccent : Colors.redAccent;
    final text = online ? '$label online' : '$label offline';

    return InkWell(
      borderRadius: BorderRadius.circular(999),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: color.withValues(alpha: 0.28)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            ),
            const SizedBox(width: 6),
            Text(
              text,
              style: TextStyle(
                color: color.withValues(alpha: 0.95),
                fontSize: 12,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
