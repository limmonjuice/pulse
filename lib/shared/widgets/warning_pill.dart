// lib/shared/widgets/warning_pill.dart
import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';

/// A coral warning pill — used by AssessmentCard's "Get care if…" list
/// and VisitSummaryScreen's watch-for recap.
class WarningPill extends StatelessWidget {
  const WarningPill({super.key, required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    final coral = Theme.of(context).extension<UrgencyColors>()!.seekCareNow;
    return Padding(
      padding: const EdgeInsets.only(bottom: 7),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10),
        decoration: BoxDecoration(
          color: coral.tint,
          borderRadius: BorderRadius.circular(AppRadii.pillRowRadius),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.warning_amber_rounded, size: 17, color: coral.text),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                text,
                style: Theme.of(
                  context,
                ).textTheme.bodyMedium?.copyWith(color: coral.text),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
