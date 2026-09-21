#include <rclcpp/rclcpp.hpp>
#include <message_filters/subscriber.h>
#include <message_filters/time_synchronizer.h>
#include <std_msgs/Header.h>

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>("detection_listener");
  // Simplified detection listener
  RCLCPP_INFO(node->get_logger(), "Detection listener started");
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
