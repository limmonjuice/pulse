import 'package:flutter/material.dart';

/// Pulse's primary CTA button. Wraps [ElevatedButton] with the theme's
/// button styling (see `elevatedButtonTheme` in AppTheme) so callers never
/// need to hardcode padding, radius, or color.
class AppButton extends StatelessWidget {
  const AppButton({super.key, required this.label, required this.onPressed});

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(onPressed: onPressed, child: Text(label));
  }
}
