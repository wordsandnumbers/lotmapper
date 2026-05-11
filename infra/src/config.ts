import * as pulumi from "@pulumi/pulumi";

const cfg = new pulumi.Config();

export const awsRegion = cfg.get("awsRegion") ?? "us-east-1";
export const appInstanceType = cfg.get("appInstanceType") ?? "t3.small";
export const allowedSshCidr = cfg.get("allowedSshCidr") ?? "0.0.0.0/0";

// Secrets — set via: pulumi config set --secret <key> <value>
export const secretKey = cfg.requireSecret("secretKey");
export const dbPassword = cfg.requireSecret("dbPassword");
export const rabbitmqUser = cfg.requireSecret("rabbitmqUser");
export const rabbitmqPass = cfg.requireSecret("rabbitmqPass");
export const googleMapsApiKey = cfg.requireSecret("googleMapsApiKey");
export const corsOrigins = cfg.get("corsOrigins") ?? '["https://example.com"]';
