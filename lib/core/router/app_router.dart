import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/providers/auth_provider.dart';
import '../../features/auth/screens/login_screen.dart';
import '../../features/auth/screens/signup_screen.dart';
import '../../features/chat/screens/chat_screen.dart';
import '../../features/history/screens/history_screen.dart';
import '../../features/home/screens/home_screen.dart';
import '../../features/onboarding/providers/onboarding_provider.dart';
import '../../features/onboarding/screens/disclaimer_screen.dart';
import '../../features/profile/screens/profile_list_screen.dart';
import '../../features/settings/screens/settings_screen.dart';
import '../../features/visit_summary/screens/visit_summary_screen.dart';

/// Route paths used across the app. Centralized so screens navigate via
/// `context.go(AppRoutes.chat)` instead of hardcoded path strings.
class AppRoutes {
  AppRoutes._();

  static const disclaimer = '/disclaimer';
  static const login = '/login';
  static const signup = '/signup';
  static const home = '/home';
  static const chat = '/chat';
  static const history = '/history';
  static const family = '/family';
  static const settings = '/settings';
  static const visitSummary = '/visit-summary';
}

final GlobalKey<NavigatorState> _rootNavigatorKey = GlobalKey<NavigatorState>();
final GlobalKey<NavigatorState> _shellNavigatorKey =
    GlobalKey<NavigatorState>();

/// Notifies go_router's `redirect` to re-run whenever a stream emits, so
/// routing reacts to auth-state changes that don't originate from
/// in-app navigation (e.g. a token expiring or `signOut()` completing).
class GoRouterRefreshStream extends ChangeNotifier {
  GoRouterRefreshStream(Stream<dynamic> stream) {
    notifyListeners();
    _subscription = stream.listen((_) => notifyListeners());
  }

  late final StreamSubscription<dynamic> _subscription;

  @override
  void dispose() {
    _subscription.cancel();
    super.dispose();
  }
}

/// Pulse's app-wide router. Onboarding and auth sit outside the bottom-nav
/// shell; the five main tabs (Home, Chat, History, Family, Settings) share
/// a persistent bottom nav via [StatefulShellRoute].
final appRouterProvider = Provider<GoRouter>((ref) {
  final authRepository = ref.watch(authRepositoryProvider);
  final refreshStream = GoRouterRefreshStream(authRepository.authStateChanges);
  ref.onDispose(refreshStream.dispose);

  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: AppRoutes.disclaimer,
    refreshListenable: refreshStream,
    redirect: (context, state) {
      final loggedIn = authRepository.currentUser != null;
      final disclaimerAccepted = ref.read(disclaimerAcceptedProvider);
      final location = state.matchedLocation;

      final onDisclaimer = location == AppRoutes.disclaimer;
      final onAuthScreen =
          location == AppRoutes.login || location == AppRoutes.signup;

      if (!disclaimerAccepted) {
        return onDisclaimer ? null : AppRoutes.disclaimer;
      }
      if (onDisclaimer) {
        // Already accepted this session — nothing left to show here.
        return loggedIn ? AppRoutes.home : AppRoutes.login;
      }
      if (!loggedIn) {
        return onAuthScreen ? null : AppRoutes.login;
      }
      if (onAuthScreen) {
        return AppRoutes.home;
      }
      return null;
    },
    routes: [
      GoRoute(
        path: AppRoutes.disclaimer,
        builder: (context, state) => const DisclaimerScreen(),
      ),
      GoRoute(
        path: AppRoutes.login,
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: AppRoutes.signup,
        builder: (context, state) => const SignupScreen(),
      ),
      GoRoute(
        path: AppRoutes.visitSummary,
        builder: (context, state) => const VisitSummaryScreen(),
      ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) {
          return _AppShell(navigationShell: navigationShell);
        },
        branches: [
          StatefulShellBranch(
            navigatorKey: _shellNavigatorKey,
            routes: [
              GoRoute(
                path: AppRoutes.home,
                builder: (context, state) => const HomeScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.chat,
                builder: (context, state) => const ChatScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.history,
                builder: (context, state) => const HistoryScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.family,
                builder: (context, state) => const ProfileListScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.settings,
                builder: (context, state) => const SettingsScreen(),
              ),
            ],
          ),
        ],
      ),
    ],
  );
});

/// Persistent bottom nav shell shown across the five main tabs.
class _AppShell extends StatelessWidget {
  const _AppShell({required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: navigationShell.currentIndex,
        onDestinationSelected: (index) => navigationShell.goBranch(
          index,
          initialLocation: index == navigationShell.currentIndex,
        ),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), label: 'Home'),
          NavigationDestination(
            icon: Icon(Icons.chat_bubble_outline),
            label: 'Chat',
          ),
          NavigationDestination(icon: Icon(Icons.history), label: 'History'),
          NavigationDestination(
            icon: Icon(Icons.group_outlined),
            label: 'Family',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            label: 'Settings',
          ),
        ],
      ),
    );
  }
}
