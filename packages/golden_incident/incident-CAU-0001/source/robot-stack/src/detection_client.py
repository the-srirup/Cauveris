"""
ROS 2 Detection Client with QoS Subscription.
"""
class DetectionClient:
    def __init__(self, freshness_budget_ms=120):
        self.freshness_budget_ms = freshness_budget_ms
        self.qos_depth = 10
        self.keep_last = True

    def validate_freshness(self, timestamp_ms, current_time_ms):
        age_ms = current_time_ms - timestamp_ms
        if age_ms > self.freshness_budget_ms:
            return False, f"Detection stale by {age_ms - self.freshness_budget_ms}ms"
        return True, "Fresh"
