import 'package:flutter/material.dart';

class ProfileListScreen extends StatelessWidget {
  const ProfileListScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Family')),
      body: Center(
        child: Text(
          'Profile list screen — TODO',
          style: theme.textTheme.titleLarge,
        ),
      ),
    );
  }
}
