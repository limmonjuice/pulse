import 'package:flutter/material.dart';

/// Circular avatar for a household profile. Used in Home, Family, and
/// Settings. Color cycling through `AppColors.avatarAccents` and real
/// initials/photo logic are wired up when the profile feature is built.
class ProfileAvatar extends StatelessWidget {
  const ProfileAvatar({super.key, required this.initials, this.radius = 20});

  final String initials;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return CircleAvatar(radius: radius, child: Text(initials));
  }
}
