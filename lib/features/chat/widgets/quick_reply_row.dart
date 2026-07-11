import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// A single non-wrapping, horizontally scrollable row of quick-reply
/// chips shown below a question turn. Tapping a chip sends its label as
/// the user's next message.
class QuickReplyRow extends StatelessWidget {
  const QuickReplyRow({
    super.key,
    required this.options,
    required this.onSelect,
  });

  final List<String> options;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      reverse:
          true, // anchors to the right, matching the design, even if it overflows
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final option in options) ...[
            OutlinedButton(
              onPressed: () => onSelect(option),
              style: OutlinedButton.styleFrom(
                backgroundColor: AppColors.surface,
                side: const BorderSide(color: AppColors.chipBorder, width: 1.5),
                foregroundColor: AppColors.primaryInk,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadii.pill),
                ),
                padding: const EdgeInsets.symmetric(
                  horizontal: 13,
                  vertical: 8,
                ),
                textStyle: theme.textTheme.titleMedium?.copyWith(fontSize: 13),
              ),
              child: Text(option),
            ),
            const SizedBox(width: 7),
          ],
        ],
      ),
    );
  }
}
