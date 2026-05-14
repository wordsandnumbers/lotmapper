import * as aws from "@pulumi/aws";
import { subnet } from "./vpc";
import { appSg } from "./security-groups";
import { ec2InstanceProfile } from "./iam";
import { appInstanceType } from "./config";

export const cluster = new aws.ecs.Cluster("parking-lot-cluster", {
    name: "parking-lot",
    tags: { Name: "parking-lot-cluster" },
});

// ECS-optimized Amazon Linux 2023 AMI
const ecsAmi = aws.ec2.getAmi({
    mostRecent: true,
    owners: ["amazon"],
    filters: [
        { name: "name", values: ["al2023-ami-ecs-hvm-*-x86_64"] },
        { name: "state", values: ["available"] },
    ],
});

const userData = cluster.name.apply(clusterName =>
    Buffer.from(`#!/bin/bash
echo ECS_CLUSTER=${clusterName} >> /etc/ecs/ecs.config
echo ECS_ENABLE_CONTAINER_METADATA=true >> /etc/ecs/ecs.config
`).toString("base64")
);

export const appInstance = new aws.ec2.Instance("parking-lot-app-server", {
    ami: ecsAmi.then(ami => ami.id),
    instanceType: appInstanceType,
    subnetId: subnet.id,
    vpcSecurityGroupIds: [appSg.id],
    iamInstanceProfile: ec2InstanceProfile.name,
    userData: userData,
    rootBlockDevice: {
        volumeType: "gp3",
        volumeSize: 30,
        deleteOnTermination: true,
    },
    tags: { Name: "parking-lot-app-server" },
});

export const eip = new aws.ec2.Eip("parking-lot-eip", {
    instance: appInstance.id,
    tags: { Name: "parking-lot-eip" },
});
