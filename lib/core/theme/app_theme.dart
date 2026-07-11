// lib/core/theme/app_theme.dart
//
// Single source of truth for Pulse's visual design tokens, generated
// directly from design-system.md. Do not hardcode colors, radii, or type
// styles anywhere else in the app — import from here instead.
//
// Requires the `google_fonts` package (Nunito + Inter aren't Flutter
// defaults):  flutter pub add google_fonts

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Core color tokens.
class AppColors {
  AppColors._();

  // Surfaces
  static const Color bgCream = Color(0xFFFBF7F0);
  static const Color surface = Color(0xFFFFFFFF);

  // Brand
  static const Color primary = Color(0xFF6FA8B5);
  static const Color primaryDeep = Color(0xFF4E8A97);
  static const Color primaryInk = Color(0xFF3F7A86);
  static const Color tintTeal = Color(0xFFEAF3F4);

  // Text
  static const Color text = Color(0xFF33403F);
  static const Color textBody = Color(0xFF5C6866);
  static const Color textMuted = Color(0xFF7C8887);
  static const Color textMutedAlt = Color(0xFF8B9694);
  static const Color textFaint = Color(0xFFA9B0AE);
  static const Color textFaintAlt = Color(0xFFA0AAA9);
  static const Color navInactive = Color(0xFFADB4B1);
  static const Color labelEyebrow = Color(0xFFA69C82);

  // Lines & borders
  static const Color divider = Color(0xFFF0E9DD);
  static const Color dividerAlt = Color(0xFFF5EFE4);
  static const Color dashed = Color(0xFFCBBFA0);
  static const Color chipBorder = Color(0xFFBBD7DD);
  static const Color chevron = Color(0xFFC3CBC9);

  // Toggle
  static const Color toggleOff = Color(0xFFE4DDD0);

  // --- Chat-screen extensions (2026-07-10) — see PULSE_DESIGN_SYSTEM.md §8 ---
  static const Color crisisHeading = Color(0xFF2F4A4F);
  static const Color crisisBody = Color(0xFF3F5559);
  static const Color crisisFooterText = Color(0xFF7C9296);

  // --- AssessmentCard self-care checklist (2026-07-10, found while
  // implementing Task 14 — these 4 mockup colors were never tokenized
  // in the original Task 4 pass) — see PULSE_DESIGN_SYSTEM.md §8.
  static const Color selfCareRowBg = Color(0xFFF8F5EE);
  // Numerically equal to UrgencyColors.monitorAtHome.solid (sage) — kept
  // as its own token rather than reusing that extension, since a
  // checked-off self-care item is a "done" state, not an urgency read;
  // the two concepts should stay decoupled even though the mockup
  // happens to reuse the same green.
  static const Color selfCareChecked = Color(0xFF8FB89A);
  static const Color selfCareUncheckedBorder = Color(0xFFCFD9D1);
  static const Color selfCareCheckedText = Color(0xFF9BA6A2);

  /// Household-profile avatar accents. Cycle through these in order as
  /// profiles are created — do not assign colors arbitrarily.
  static const List<Color> avatarAccents = [
    primary, // teal
    Color(0xFFB9A6D6), // lavender
    Color(0xFF8FB89A), // sage
    Color(0xFFE8B04B), // honey
  ];
}

/// The three urgency tiers Pulse's entire core loop hinges on.
/// Never introduce a fourth tier or a raw "danger red" outside this set.
enum UrgencyLevel { monitorAtHome, seeDoctorSoon, seekCareNow }

class UrgencyPalette {
  final Color solid;
  final Color tint;
  final Color text;
  const UrgencyPalette({
    required this.solid,
    required this.tint,
    required this.text,
  });
}

/// ThemeExtension so urgency colors are pulled via
/// `Theme.of(context).extension<UrgencyColors>()!.forLevel(level)`
/// instead of being hardcoded in chat/history widgets.
class UrgencyColors extends ThemeExtension<UrgencyColors> {
  final UrgencyPalette monitorAtHome;
  final UrgencyPalette seeDoctorSoon;
  final UrgencyPalette seekCareNow;

  const UrgencyColors({
    required this.monitorAtHome,
    required this.seeDoctorSoon,
    required this.seekCareNow,
  });

  static const UrgencyColors standard = UrgencyColors(
    monitorAtHome: UrgencyPalette(
      solid: Color(0xFF8FB89A),
      tint: Color(0xFFEBF3ED),
      text: Color(0xFF4F7A5E),
    ),
    seeDoctorSoon: UrgencyPalette(
      solid: Color(0xFFE8B04B),
      tint: Color(0xFFFBF1DC),
      text: Color(0xFFB07E17),
    ),
    seekCareNow: UrgencyPalette(
      solid: Color(0xFFE07856),
      tint: Color(0xFFFBEAE3),
      text: Color(0xFFC85A38),
    ),
  );

  UrgencyPalette forLevel(UrgencyLevel level) {
    switch (level) {
      case UrgencyLevel.monitorAtHome:
        return monitorAtHome;
      case UrgencyLevel.seeDoctorSoon:
        return seeDoctorSoon;
      case UrgencyLevel.seekCareNow:
        return seekCareNow;
    }
  }

  @override
  UrgencyColors copyWith({
    UrgencyPalette? monitorAtHome,
    UrgencyPalette? seeDoctorSoon,
    UrgencyPalette? seekCareNow,
  }) {
    return UrgencyColors(
      monitorAtHome: monitorAtHome ?? this.monitorAtHome,
      seeDoctorSoon: seeDoctorSoon ?? this.seeDoctorSoon,
      seekCareNow: seekCareNow ?? this.seekCareNow,
    );
  }

  @override
  UrgencyColors lerp(ThemeExtension<UrgencyColors>? other, double t) {
    // These are discrete semantic tiers, not a continuous scale —
    // there's nothing meaningful to interpolate between them.
    if (other is! UrgencyColors) return this;
    return t < 0.5 ? this : other;
  }
}

/// Radii — pulled directly from the approved prototype, not Material
/// defaults.
class AppRadii {
  AppRadii._();
  static const double button = 20;
  static const double buttonInCard = 15.5;
  static const double card = 24;
  static const double chatBubble = 22;
  static const double chatBubbleTail = 8;
  static const double pill = 999;
  static const double iconChip = 15;
  static const double navBarTop = 26;

  // --- Chat-screen extensions (2026-07-10) — see PULSE_DESIGN_SYSTEM.md §8 ---
  static const double crisisCard = 28;
  static const double cardRowRadius = 14;
  static const double pillRowRadius = 13;
}

/// Spacing scale matching the design system's stated values.
class AppSpacing {
  AppSpacing._();
  static const double screenPadding = 24;
  static const double cardPaddingMin = 16;
  static const double cardPaddingMax = 22;
  static const double sectionGap = 24;
  static const double groupGap = 12;
  static const double minTouchTarget = 44;
}

/// Soft, cool-gray shadows — never harsh black. Use these constants
/// instead of hand-rolling BoxShadow values per-widget.
class AppShadows {
  AppShadows._();

  static List<BoxShadow> card = [
    BoxShadow(
      color: const Color(0xFF506464).withOpacity(0.08),
      blurRadius: 22,
      offset: const Offset(0, 8),
    ),
  ];

  static List<BoxShadow> cardRaised = [
    BoxShadow(
      color: const Color(0xFF6FA8B5).withOpacity(0.16),
      blurRadius: 26,
      offset: const Offset(0, 10),
    ),
  ];

  static List<BoxShadow> urgencyCard = [
    BoxShadow(
      color: const Color(0xFF505050).withOpacity(0.18),
      blurRadius: 36,
      offset: const Offset(0, 16),
    ),
  ];

  static List<BoxShadow> ctaButton = [
    BoxShadow(
      color: const Color(0xFF4E8A97).withOpacity(0.38),
      blurRadius: 26,
      offset: const Offset(0, 12),
    ),
  ];

  static List<BoxShadow> navBarTop = [
    BoxShadow(
      color: const Color(0xFF506464).withOpacity(0.06),
      blurRadius: 20,
      offset: const Offset(0, -6),
    ),
  ];

  // --- Chat-screen extensions (2026-07-10) — see PULSE_DESIGN_SYSTEM.md §8 ---
  static List<BoxShadow> crisisCard = [
    BoxShadow(
      color: AppColors.primary.withOpacity(0.18),
      blurRadius: 30,
      offset: const Offset(0, 12),
    ),
  ];

  static List<BoxShadow> userBubble = [
    BoxShadow(
      color: AppColors.primary.withOpacity(0.28),
      blurRadius: 16,
      offset: const Offset(0, 6),
    ),
  ];
}

/// Assembled ThemeData for Pulse.
///
/// Usage in app.dart:
///   MaterialApp.router(theme: AppTheme.light, ...)
///
/// Note: if `CardThemeData` doesn't resolve on your installed Flutter
/// version, your SDK may still expect the older `CardTheme` class name —
/// check `flutter --version` against current Flutter theming docs if so.
class AppTheme {
  AppTheme._();

  static ThemeData get light {
    final base = ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: AppColors.bgCream,
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppColors.primary,
        brightness: Brightness.light,
        primary: AppColors.primaryDeep,
        surface: AppColors.surface,
      ),
    );

    final headingFont = GoogleFonts.nunitoTextTheme(base.textTheme);
    final bodyFont = GoogleFonts.interTextTheme(base.textTheme);

    return base.copyWith(
      textTheme: bodyFont.copyWith(
        // Wordmark ("Pulse" on onboarding)
        displayLarge: headingFont.displayLarge?.copyWith(
          fontWeight: FontWeight.w800,
          fontSize: 42,
          letterSpacing: -0.5,
          color: AppColors.text,
        ),
        // Screen titles ("History", greeting)
        headlineLarge: headingFont.headlineLarge?.copyWith(
          fontWeight: FontWeight.w800,
          fontSize: 25,
          color: AppColors.text,
        ),
        // Card / section headings
        titleLarge: headingFont.titleLarge?.copyWith(
          fontWeight: FontWeight.w700,
          fontSize: 18,
          color: AppColors.text,
        ),
        // List row titles
        titleMedium: headingFont.titleMedium?.copyWith(
          fontWeight: FontWeight.w700,
          fontSize: 15,
          color: AppColors.text,
        ),
        // Chat-screen extension (2026-07-10): in-card group headers
        // ("Things you can do today", "Check in on yourself", "Get
        // care if…") — see PULSE_DESIGN_SYSTEM.md §8.
        titleSmall: headingFont.titleSmall?.copyWith(
          fontWeight: FontWeight.w700,
          fontSize: 13.5,
          color: AppColors.text,
        ),
        // Chat-screen extension (2026-07-10): the "PULSE GUIDANCE"
        // meta-label on the assessment card — distinct from the
        // Section-eyebrow style below (Inter, not Nunito; smaller).
        labelMedium: bodyFont.labelMedium?.copyWith(
          fontWeight: FontWeight.w600,
          fontSize: 10.5,
          letterSpacing: 0.6,
          color: AppColors.textFaint,
        ),
        // Section eyebrows (UPPERCASE) — apply
        // `.copyWith(letterSpacing: 0.55)` + manual uppercase in the widget
        labelSmall: headingFont.labelSmall?.copyWith(
          fontWeight: FontWeight.w700,
          fontSize: 12.5,
          letterSpacing: 0.55,
          color: AppColors.labelEyebrow,
        ),
        // Body copy / chat bubble text
        bodyMedium: bodyFont.bodyMedium?.copyWith(
          fontWeight: FontWeight.w400,
          fontSize: 14.5,
          height: 1.55,
          color: AppColors.textBody,
        ),
        // Meta / timestamp text
        bodySmall: bodyFont.bodySmall?.copyWith(
          fontWeight: FontWeight.w500,
          fontSize: 12,
          color: AppColors.textMuted,
        ),
        // Button labels
        labelLarge: headingFont.labelLarge?.copyWith(
          fontWeight: FontWeight.w700,
          fontSize: 16,
          color: Colors.white,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primaryDeep,
          foregroundColor: Colors.white,
          minimumSize: const Size.fromHeight(58),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadii.button),
          ),
          textStyle: GoogleFonts.nunito(
            fontWeight: FontWeight.w700,
            fontSize: 16,
          ),
        ),
      ),
      cardTheme: CardThemeData(
        color: AppColors.surface,
        elevation: 0, // shadows applied manually via AppShadows for control
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.card),
        ),
        margin: EdgeInsets.zero,
      ),
      dividerTheme: const DividerThemeData(
        color: AppColors.divider,
        thickness: 1,
        space: 1,
      ),
      // Chat-screen extension (2026-07-10) follow-up: pins the bottom
      // nav's label style explicitly. Needed because NavigationBar's
      // Material 3 default resolves label text style from
      // textTheme.labelMedium (only the color gets overridden via
      // .apply()) — without this override, adding a chat-specific
      // labelMedium style above would silently restyle the live bottom
      // nav bar. Values match PULSE_DESIGN_SYSTEM.md §5 "Bottom nav".
      navigationBarTheme: NavigationBarThemeData(
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return GoogleFonts.nunito(
            fontSize: 10,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w600,
            color: selected ? AppColors.primaryInk : AppColors.navInactive,
          );
        }),
      ),
      extensions: const [UrgencyColors.standard],
    );
  }
}
