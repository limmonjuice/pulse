// lib/features/chat/widgets/urgency_strip.dart
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// The pinned guidance strip (conversation engine v2, spec §9): a compact,
/// always-visible reminder of the active recommendation, shown under the
/// app bar while an assessment is active. The full AssessmentCard stays in
/// the transcript; this is what makes "the person can already see the
/// card" literally true once it has scrolled away.
///
/// Rendering only — visibility (assessment active, not in crisis mode) is
/// the chat screen's decision, driven by the server's conversation_state.
/// Tier color is always paired with the text label, never color alone
/// (accessibility rule, AGENTS.md).
class UrgencyStrip extends StatelessWidget {
  const UrgencyStrip({
    super.key,
    required this.urgency,
    this.nextStep,
    this.onTap,
  });

  final UrgencyLevel urgency;
  final String? nextStep;
  final VoidCallback? onTap;

  // Deliberately mirrors AssessmentCard's private tier maps — two small
  // widget-local maps beat a premature shared constants module while only
  // these two widgets need them.
  static const Map<UrgencyLevel, IconData> _tierIcon = {
    UrgencyLevel.monitorAtHome: Icons.check_rounded,
    UrgencyLevel.seeDoctorSoon: Icons.access_time_rounded,
    UrgencyLevel.seekCareNow: Icons.priority_high_rounded,
  };

  static const Map<UrgencyLevel, String> _tierLabel = {
    UrgencyLevel.monitorAtHome: 'Monitor at home',
    UrgencyLevel.seeDoctorSoon: 'See a doctor soon',
    UrgencyLevel.seekCareNow: 'Seek care now',
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final palette = theme.extension<UrgencyColors>()!.forLevel(urgency);

    return Material(
      color: palette.solid.withValues(alpha: 0.12),
      child: InkWell(
        onTap: onTap,
        child: Container(
          width: double.infinity,
          constraints: const BoxConstraints(minHeight: 44),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            border: Border(left: BorderSide(color: palette.solid, width: 4)),
          ),
          child: Row(
            children: [
              Icon(_tierIcon[urgency], size: 18, color: palette.text),
              const SizedBox(width: 8),
              Expanded(
                child: Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(
                        text: _tierLabel[urgency],
                        style: theme.textTheme.labelLarge?.copyWith(
                          color: palette.text,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      if (nextStep != null)
                        TextSpan(
                          text: ' · $nextStep',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: palette.text,
                          ),
                        ),
                    ],
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Icon(Icons.chevron_right_rounded, size: 18, color: palette.text),
            ],
          ),
        ),
      ),
    );
  }
}
