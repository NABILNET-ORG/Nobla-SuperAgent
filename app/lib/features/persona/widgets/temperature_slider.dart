import 'package:flutter/material.dart';

class TemperatureSlider extends StatelessWidget {
  final double? value;
  final ValueChanged<double?> onChanged;

  const TemperatureSlider({
    super.key,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final currentValue = value ?? 0.0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text('Temperature Bias', style: theme.textTheme.titleSmall),
            const Spacer(),
            Text(
              currentValue == 0.0
                  ? 'Neutral'
                  : currentValue > 0
                      ? '+${currentValue.toStringAsFixed(1)} Creative'
                      : '${currentValue.toStringAsFixed(1)} Focused',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
        Slider(
          value: currentValue,
          min: -0.5,
          max: 0.5,
          divisions: 10,
          label: currentValue.toStringAsFixed(1),
          onChanged: (v) => onChanged(v == 0.0 ? null : v),
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Focused', style: theme.textTheme.labelSmall),
            Text('Creative', style: theme.textTheme.labelSmall),
          ],
        ),
      ],
    );
  }
}
