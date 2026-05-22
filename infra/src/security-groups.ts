import * as aws from "@pulumi/aws";
import { vpc } from "./vpc";
import { allowedSshCidr } from "./config";

export const appSg = new aws.ec2.SecurityGroup("parking-lot-sg", {
    vpcId: vpc.id,
    description: "Parking lot app server",
    ingress: [
        { protocol: "tcp", fromPort: 80,   toPort: 80,   cidrBlocks: ["0.0.0.0/0"] },
        { protocol: "tcp", fromPort: 443,  toPort: 443,  cidrBlocks: ["0.0.0.0/0"] },
        { protocol: "tcp", fromPort: 22,   toPort: 22,   cidrBlocks: [allowedSshCidr] },
    ],
    egress: [
        { protocol: "-1", fromPort: 0, toPort: 0, cidrBlocks: ["0.0.0.0/0"] },
    ],
    tags: { Name: "parking-lot-sg" },
});
