output "dns_record" {
  description = "The Route 53 record that points the custom domain at Firebase Hosting."
  value       = "${aws_route53_record.app.type} ${aws_route53_record.app.fqdn} → ${one(aws_route53_record.app.records)}"
}
