// lib/features/chat/widgets/assessment_card.dart
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../shared/widgets/checklist_row.dart';
import '../../../shared/widgets/warning_pill.dart';
import '../models/urgency_result.dart';

/// The flagship assessment card: tier icon chip + label + eyebrow,
/// explanation, "What to do next", a tappable self-care checklist,
/// monitoring rows, watch-for warning pills, a tier-solid CTA button,
/// and a de-emphasized encouragement line. Every list-backed section
/// (self_care, monitoring, watch_for) disappears entirely when empty.
///
/// Only ever built for `result.type == ChatTurnType.assessment`, which
/// guarantees `result.urgency` is non-null (see UrgencyResult.fromJson).
class AssessmentCard extends StatelessWidget {
  const AssessmentCard({
    super.key,
    required this.result,
    required this.checkedSelfCare,
    required this.onToggleSelfCare,
    this.isUpdate = false,
  });

  final UrgencyResult result;
  final Set<int> checkedSelfCare;
  final ValueChanged<int> onToggleSelfCare;

  /// Engine v2: true when the server's card directive was "update" — the
  /// eyebrow says so, so a changed recommendation reads as a change, not
  /// a repeat.
  final bool isUpdate;

  static const Map<UrgencyLevel, String> _ctaCopy = {
    // Deliberately NOT "Set a check-in reminder" (that implies the
    // manually configured medication-reminder engine, explicitly
    // deferred past MVP per AGENTS.md). The real MVP-adjacent mechanic
    // is Pulse's automatic, proactive follow-up — passive, not
    // something a button "sets."
    UrgencyLevel.monitorAtHome: "Okay — I'll check in on this tomorrow.",
    UrgencyLevel.seeDoctorSoon: 'Book a GP visit',
    UrgencyLevel.seekCareNow: 'Find urgent care nearby',
  };

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
    final urgency = result.urgency!;
    final palette = theme.extension<UrgencyColors>()!.forLevel(urgency);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.cardPaddingMax),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadii.card),
        boxShadow: AppShadows.urgencyCard,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: palette.solid,
                  borderRadius: BorderRadius.circular(AppRadii.iconChip),
                ),
                child: Icon(_tierIcon[urgency], color: Colors.white),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _tierLabel[urgency]!,
                      style: theme.textTheme.titleLarge?.copyWith(
                        color: palette.text,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      isUpdate ? 'UPDATED · PULSE GUIDANCE' : 'PULSE GUIDANCE',
                      style: theme.textTheme.labelMedium,
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (result.explanation != null) ...[
            const SizedBox(height: 14),
            Text(result.explanation!, style: theme.textTheme.bodyMedium),
          ],
          if (result.nextStep != null) ...[
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 13),
              child: Divider(height: 1),
            ),
            Text('What to do next', style: theme.textTheme.titleSmall),
            const SizedBox(height: 4),
            Text(result.nextStep!, style: theme.textTheme.bodyMedium),
          ],
          if (result.selfCare.isNotEmpty) ...[
            const SizedBox(height: 18),
            Text('Things you can do today', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            for (var i = 0; i < result.selfCare.length; i++)
              ChecklistRow(
                text: result.selfCare[i],
                done: checkedSelfCare.contains(i),
                onTap: () => onToggleSelfCare(i),
              ),
          ],
          if (result.monitoring.isNotEmpty) ...[
            const SizedBox(height: 18),
            Text('Check in on yourself', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            for (final m in result.monitoring) ChecklistRow(text: m),
          ],
          if (result.watchFor.isNotEmpty) ...[
            const SizedBox(height: 18),
            Text('Get care if…', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            for (final w in result.watchFor) WarningPill(text: w),
          ],
          const SizedBox(height: 18),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              // TODO(care-finder): wire once the care-finder feature exists.
              // Visual affordance only this pass.
              onPressed: () {},
              style: ElevatedButton.styleFrom(
                backgroundColor: palette.solid,
                foregroundColor: Colors.white,
                minimumSize: const Size.fromHeight(50),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadii.buttonInCard),
                ),
              ),
              child: Text(_ctaCopy[urgency]!),
            ),
          ),
          if (result.encouragement != null) ...[
            const SizedBox(height: 12),
            Text(
              result.encouragement!,
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall?.copyWith(
                color: AppColors.textFaintAlt,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
