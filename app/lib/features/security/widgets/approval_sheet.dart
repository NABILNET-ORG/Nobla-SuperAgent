import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/features/security/providers/approval_provider.dart';

/// Shows the approval bottom sheet for the given [notifier] provider.
///
/// Returns `true` if the user approved, `false` otherwise (deny / dismiss /
/// timeout).  The caller is responsible for holding the [StateNotifierProvider]
/// that owns the [ApprovalNotifier].
Future<bool> showApprovalSheet(
  BuildContext context, {
  required ApprovalRequest request,
  required StateNotifierProvider<ApprovalNotifier, ApprovalState> provider,
}) async {
  // Haptic feedback on appear.
  HapticFeedback.mediumImpact();

  final result = await showModalBottomSheet<bool>(
    context: context,
    isDismissible: true,
    enableDrag: true,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => _ApprovalSheetContent(
      request: request,
      provider: provider,
    ),
  );

  // Swipe-down dismiss (null) counts as deny.
  return result ?? false;
}

// ---------------------------------------------------------------------------
// Sheet content
// ---------------------------------------------------------------------------

class _ApprovalSheetContent extends ConsumerStatefulWidget {
  final ApprovalRequest request;
  final StateNotifierProvider<ApprovalNotifier, ApprovalState> provider;

  const _ApprovalSheetContent({
    required this.request,
    required this.provider,
  });

  @override
  ConsumerState<_ApprovalSheetContent> createState() =>
      _ApprovalSheetContentState();
}

class _ApprovalSheetContentState extends ConsumerState<_ApprovalSheetContent> {
  bool _paramsExpanded = false;

  @override
  Widget build(BuildContext context) {
    final approvalState = ref.watch(widget.provider);
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final remaining = approvalState.remainingSeconds;
    final timeout = widget.request.timeoutSeconds;
    final progress = timeout > 0 ? remaining / timeout : 0.0;

    // If the current request changed (processed elsewhere), pop.
    if (approvalState.current?.requestId != widget.request.requestId) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) Navigator.of(context).pop(false);
      });
    }

    return SafeArea(
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        decoration: BoxDecoration(
          color: colorScheme.surface,
          borderRadius: const BorderRadius.all(Radius.circular(20)),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Drag handle
              Container(
                width: 40,
                height: 4,
                margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(
                  color: colorScheme.onSurfaceVariant.withValues(alpha: 0.4),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),

              // Header
              Row(
                children: [
                  Icon(Icons.lock_outline, color: colorScheme.error, size: 22),
                  const SizedBox(width: 8),
                  Text(
                    'Approval Required',
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),

              // Tool name
              Align(
                alignment: Alignment.centerLeft,
                child: Chip(
                  avatar: const Icon(Icons.build_outlined, size: 16),
                  label: Text(
                    widget.request.toolName,
                    style: theme.textTheme.labelLarge,
                  ),
                  backgroundColor:
                      colorScheme.secondaryContainer.withValues(alpha: 0.6),
                  side: BorderSide.none,
                ),
              ),
              const SizedBox(height: 8),

              // Description
              if (widget.request.description.isNotEmpty)
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    widget.request.description,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              const SizedBox(height: 12),

              // Expandable params card
              if (widget.request.paramsSummary.isNotEmpty)
                _buildParamsCard(theme, colorScheme),
              const SizedBox(height: 20),

              // Countdown timer
              _buildCountdown(theme, colorScheme, remaining, progress),
              const SizedBox(height: 20),

              // Action buttons
              _buildActions(theme, colorScheme),
            ],
          ),
        ),
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Sub-widgets
  // ---------------------------------------------------------------------------

  Widget _buildParamsCard(ThemeData theme, ColorScheme cs) {
    final prettyParams = const JsonEncoder.withIndent('  ')
        .convert(widget.request.paramsSummary);
    return Card(
      margin: EdgeInsets.zero,
      color: cs.surfaceContainerHighest.withValues(alpha: 0.5),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      clipBehavior: Clip.antiAlias,
      child: ExpansionTile(
        initiallyExpanded: _paramsExpanded,
        onExpansionChanged: (v) => setState(() => _paramsExpanded = v),
        tilePadding: const EdgeInsets.symmetric(horizontal: 12),
        title: Text('Parameters', style: theme.textTheme.labelLarge),
        leading: const Icon(Icons.data_object, size: 18),
        childrenPadding:
            const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        children: [
          SizedBox(
            width: double.infinity,
            child: Text(
              prettyParams,
              style: theme.textTheme.bodySmall?.copyWith(
                fontFamily: 'monospace',
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCountdown(
    ThemeData theme,
    ColorScheme cs,
    int remaining,
    double progress,
  ) {
    final isUrgent = remaining <= 5;
    final color = isUrgent ? cs.error : cs.primary;
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        SizedBox(
          width: 48,
          height: 48,
          child: Stack(
            alignment: Alignment.center,
            children: [
              CircularProgressIndicator(
                value: progress,
                strokeWidth: 3.5,
                backgroundColor: cs.surfaceContainerHighest,
                color: color,
              ),
              Text(
                '$remaining',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        Text(
          isUrgent ? 'Expiring soon...' : 'seconds remaining',
          style: theme.textTheme.bodySmall?.copyWith(
            color: isUrgent ? cs.error : cs.onSurfaceVariant,
          ),
        ),
      ],
    );
  }

  Widget _buildActions(ThemeData theme, ColorScheme cs) {
    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed: () {
              HapticFeedback.lightImpact();
              ref.read(widget.provider.notifier).deny(
                    widget.request.requestId,
                  );
              Navigator.of(context).pop(false);
            },
            icon: const Icon(Icons.close),
            label: const Text('Deny'),
            style: OutlinedButton.styleFrom(
              foregroundColor: cs.error,
              side: BorderSide(color: cs.error.withValues(alpha: 0.5)),
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: FilledButton.icon(
            onPressed: () {
              HapticFeedback.mediumImpact();
              ref.read(widget.provider.notifier).approve(
                    widget.request.requestId,
                  );
              Navigator.of(context).pop(true);
            },
            icon: const Icon(Icons.check),
            label: const Text('Approve'),
            style: FilledButton.styleFrom(
              backgroundColor: cs.primary,
              foregroundColor: cs.onPrimary,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
