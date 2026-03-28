import 'package:flutter/material.dart';
import 'package:nobla_agent/features/automation/models/workflow_models.dart';

/// Color scheme for step types.
Color stepTypeColor(StepType type) => switch (type) {
      StepType.tool => Colors.blue,
      StepType.agent => Colors.purple,
      StepType.condition => Colors.amber.shade700,
      StepType.webhook => Colors.green,
      StepType.delay => Colors.grey,
      StepType.approval => Colors.orange,
    };

/// Icon for step types.
IconData stepTypeIcon(StepType type) => switch (type) {
      StepType.tool => Icons.build_outlined,
      StepType.agent => Icons.smart_toy_outlined,
      StepType.condition => Icons.call_split,
      StepType.webhook => Icons.webhook_outlined,
      StepType.delay => Icons.timer_outlined,
      StepType.approval => Icons.approval_outlined,
    };

/// A single tappable node in the workflow DAG.
///
/// Visual state varies by [executionStatus]:
/// - pending: outlined border
/// - running: pulsing animation
/// - completed: solid green border
/// - failed: solid red border
/// - skipped: dimmed opacity
class StepNodeWidget extends StatelessWidget {
  final WorkflowStep step;
  final ExecutionStatus? executionStatus;
  final String? branchTaken;
  final VoidCallback? onTap;
  final double width;
  final double height;

  const StepNodeWidget({
    super.key,
    required this.step,
    this.executionStatus,
    this.branchTaken,
    this.onTap,
    this.width = 140,
    this.height = 60,
  });

  @override
  Widget build(BuildContext context) {
    final color = stepTypeColor(step.type);
    final isRunning = executionStatus == ExecutionStatus.running;
    final isSkipped = executionStatus == ExecutionStatus.skipped;

    final borderColor = switch (executionStatus) {
      ExecutionStatus.completed => Colors.green,
      ExecutionStatus.failed => Colors.red,
      ExecutionStatus.running => color,
      ExecutionStatus.skipped => Colors.grey.shade400,
      _ => color.withValues(alpha: 0.5),
    };

    final borderWidth = switch (executionStatus) {
      ExecutionStatus.completed || ExecutionStatus.failed => 2.5,
      ExecutionStatus.running => 2.5,
      _ => 1.5,
    };

    Widget node = Opacity(
      opacity: isSkipped ? 0.4 : 1.0,
      child: Container(
        key: ValueKey('node_${step.stepId}'),
        width: width,
        height: height,
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: borderColor, width: borderWidth),
          boxShadow: [
            if (!isSkipped)
              BoxShadow(
                color: borderColor.withValues(alpha: 0.2),
                blurRadius: 4,
                offset: const Offset(0, 2),
              ),
          ],
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            borderRadius: BorderRadius.circular(8),
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(stepTypeIcon(step.type), size: 14, color: color),
                      const SizedBox(width: 4),
                      Flexible(
                        child: Text(
                          step.name,
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: Theme.of(context).colorScheme.onSurface,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    step.type.label,
                    style: TextStyle(fontSize: 9, color: color),
                  ),
                  if (executionStatus != null) ...[
                    const SizedBox(height: 2),
                    _StatusDot(status: executionStatus!),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );

    if (isRunning) {
      node = _PulsingWrapper(color: color, child: node);
    }

    return node;
  }
}

/// Small colored dot indicating execution status.
class _StatusDot extends StatelessWidget {
  final ExecutionStatus status;
  const _StatusDot({required this.status});

  @override
  Widget build(BuildContext context) {
    final (color, label) = switch (status) {
      ExecutionStatus.pending => (Colors.grey, 'Pending'),
      ExecutionStatus.running => (Colors.blue, 'Running'),
      ExecutionStatus.completed => (Colors.green, 'Done'),
      ExecutionStatus.failed => (Colors.red, 'Failed'),
      ExecutionStatus.skipped => (Colors.grey, 'Skipped'),
      ExecutionStatus.paused => (Colors.orange, 'Paused'),
    };
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 3),
        Text(label, style: TextStyle(fontSize: 8, color: color)),
      ],
    );
  }
}

/// Wraps a child with a pulsing glow effect for running steps.
class _PulsingWrapper extends StatefulWidget {
  final Color color;
  final Widget child;
  const _PulsingWrapper({required this.color, required this.child});

  @override
  State<_PulsingWrapper> createState() => _PulsingWrapperState();
}

class _PulsingWrapperState extends State<_PulsingWrapper>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            boxShadow: [
              BoxShadow(
                color: widget.color
                    .withValues(alpha: 0.15 + _controller.value * 0.2),
                blurRadius: 8 + _controller.value * 8,
              ),
            ],
          ),
          child: child,
        );
      },
      child: widget.child,
    );
  }
}
