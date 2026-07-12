// lib/core/theme/contrast.dart
import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Linearizes one sRGB channel already in [0, 1], per the WCAG 2.x
/// relative luminance formula.
double _linearize(double channel) {
  return channel <= 0.03928
      ? channel / 12.92
      : math.pow((channel + 0.055) / 1.055, 2.4).toDouble();
}

/// WCAG 2.x relative luminance of [color] — 0 for black, 1 for white.
double relativeLuminance(Color color) {
  final r = _linearize(color.r);
  final g = _linearize(color.g);
  final b = _linearize(color.b);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/// WCAG 2.x contrast ratio between two colors: 1 (no contrast) to 21
/// (black on white). AA requires >= 4.5 for normal-size text, >= 3 for
/// large text (18pt+ regular / 14pt+ bold) and UI components.
double contrastRatio(Color a, Color b) {
  final lighter = math.max(relativeLuminance(a), relativeLuminance(b));
  final darker = math.min(relativeLuminance(a), relativeLuminance(b));
  return (lighter + 0.05) / (darker + 0.05);
}
