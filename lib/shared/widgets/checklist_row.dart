// lib/shared/widgets/checklist_row.dart
import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';

/// A single checklist-style row. With [onTap] set, renders a tappable
/// checkbox row (AssessmentCard's self-care checklist). With [onTap]
/// null, renders a plain, non-interactive row with a small history icon
/// instead — no per-item identity to back a "checked" state (used by
/// AssessmentCard's monitoring list and VisitSummaryScreen's read-only
/// recap sections; see the visit-summary design spec §5.3).
class ChecklistRow extends StatelessWidget {
  const ChecklistRow({
    super.key,
    required this.text,
    this.done = false,
    this.onTap,
  }) : assert(
         onTap != null || !done,
         'done has no effect without onTap — read-only rows have no per-item state to check off',
       );

  final String text;
  final bool done;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final interactive = onTap != null;
    final row = Container(
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 11),
      decoration: BoxDecoration(
        color: interactive ? AppColors.selfCareRowBg : AppColors.tintTeal,
        borderRadius: BorderRadius.circular(AppRadii.cardRowRadius),
      ),
      child: Row(
        children: [
          if (interactive)
            Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                color: done ? AppColors.selfCareChecked : Colors.white,
                borderRadius: BorderRadius.circular(8),
                border: done
                    ? null
                    : Border.all(
                        color: AppColors.selfCareUncheckedBorder,
                        width: 2,
                      ),
              ),
              child: done
                  ? const Icon(Icons.check, size: 15, color: Colors.white)
                  : null,
            )
          else
            const Icon(
              Icons.history_rounded,
              size: 15,
              color: AppColors.primaryInk,
            ),
          const SizedBox(width: 11),
          Expanded(
            child: Text(
              text,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: done ? AppColors.selfCareCheckedText : AppColors.text,
                decoration: done ? TextDecoration.lineThrough : null,
              ),
            ),
          ),
        ],
      ),
    );
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: interactive
          ? InkWell(
              onTap: onTap,
              borderRadius: BorderRadius.circular(AppRadii.cardRowRadius),
              child: row,
            )
          : row,
    );
  }
}
