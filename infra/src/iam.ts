import * as aws from "@pulumi/aws";

// EC2 instance profile — allows ECS agent to register and pull ECR images
const ec2EcsRole = new aws.iam.Role("parking-lot-ec2-role", {
    assumeRolePolicy: aws.iam.assumeRolePolicyForPrincipal({ Service: "ec2.amazonaws.com" }),
    tags: { Name: "parking-lot-ec2-role" },
});

new aws.iam.RolePolicyAttachment("parking-lot-ec2-ecs-policy", {
    role: ec2EcsRole.name,
    policyArn: "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role",
});

new aws.iam.RolePolicyAttachment("parking-lot-ec2-ssm-policy", {
    role: ec2EcsRole.name,
    policyArn: "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
});

export const ec2InstanceProfile = new aws.iam.InstanceProfile("parking-lot-instance-profile", {
    role: ec2EcsRole.name,
});

// ECS task execution role — allows ECS to pull ECR images and read Secrets Manager
export const taskExecutionRole = new aws.iam.Role("parking-lot-task-exec-role", {
    assumeRolePolicy: aws.iam.assumeRolePolicyForPrincipal({ Service: "ecs-tasks.amazonaws.com" }),
    tags: { Name: "parking-lot-task-exec-role" },
});

new aws.iam.RolePolicyAttachment("parking-lot-task-exec-policy", {
    role: taskExecutionRole.name,
    policyArn: "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
});

new aws.iam.RolePolicyAttachment("parking-lot-task-exec-secrets", {
    role: taskExecutionRole.name,
    policyArn: new aws.iam.Policy("parking-lot-secrets-policy", {
        policy: JSON.stringify({
            Version: "2012-10-17",
            Statement: [{
                Effect: "Allow",
                Action: ["secretsmanager:GetSecretValue"],
                Resource: "arn:aws:secretsmanager:*:*:secret:parking-lot/*",
            }],
        }),
    }).arn,
});

// GitHub Actions OIDC — allows pushing to ECR from CI without long-lived keys
const githubOidcProvider = new aws.iam.OpenIdConnectProvider("github-oidc", {
    url: "https://token.actions.githubusercontent.com",
    clientIdLists: ["sts.amazonaws.com"],
    thumbprintLists: ["6938fd4d98bab03faadb97b34396831e3780aea1"],
});

export const githubActionsRole = new aws.iam.Role("parking-lot-github-actions-role", {
    assumeRolePolicy: githubOidcProvider.arn.apply(arn => JSON.stringify({
        Version: "2012-10-17",
        Statement: [{
            Effect: "Allow",
            Principal: { Federated: arn },
            Action: "sts:AssumeRoleWithWebIdentity",
            Condition: {
                StringLike: {
                    "token.actions.githubusercontent.com:sub": "repo:wordsandnumbers/parking-lot-app:*",
                },
                StringEquals: {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                },
            },
        }],
    })),
    tags: { Name: "parking-lot-github-actions-role" },
});

new aws.iam.RolePolicyAttachment("parking-lot-github-ecr-policy", {
    role: githubActionsRole.name,
    policyArn: new aws.iam.Policy("parking-lot-ecr-push-policy", {
        policy: JSON.stringify({
            Version: "2012-10-17",
            Statement: [{
                Effect: "Allow",
                Action: [
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:PutImage",
                    "ecr:InitiateLayerUpload",
                    "ecr:UploadLayerPart",
                    "ecr:CompleteLayerUpload",
                    "ecr:DescribeRepositories",
                ],
                Resource: "*",
            }],
        }),
    }).arn,
});
