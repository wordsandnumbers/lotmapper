import * as aws from "@pulumi/aws";

export const vpc = new aws.ec2.Vpc("parking-lot-vpc", {
    cidrBlock: "10.0.0.0/16",
    enableDnsHostnames: true,
    enableDnsSupport: true,
    tags: { Name: "parking-lot-vpc" },
});

export const subnet = new aws.ec2.Subnet("parking-lot-subnet", {
    vpcId: vpc.id,
    cidrBlock: "10.0.1.0/24",
    availabilityZone: "us-east-1a",
    mapPublicIpOnLaunch: true,
    tags: { Name: "parking-lot-subnet-public" },
});

const igw = new aws.ec2.InternetGateway("parking-lot-igw", {
    vpcId: vpc.id,
    tags: { Name: "parking-lot-igw" },
});

const routeTable = new aws.ec2.RouteTable("parking-lot-rt", {
    vpcId: vpc.id,
    routes: [{ cidrBlock: "0.0.0.0/0", gatewayId: igw.id }],
    tags: { Name: "parking-lot-rt-public" },
});

new aws.ec2.RouteTableAssociation("parking-lot-rta", {
    subnetId: subnet.id,
    routeTableId: routeTable.id,
});
