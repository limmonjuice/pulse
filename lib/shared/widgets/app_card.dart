import 'package:flutter/material.dart';

/// Pulse's shared card container. Wraps [Card] with the theme's card
/// styling (rounded corners, white surface) plus manual soft-shadow support
/// via AppShadows — see `core/theme/app_theme.dart`.
class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
  });

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: padding,
        child: child,
      ),
    );
  }
}
