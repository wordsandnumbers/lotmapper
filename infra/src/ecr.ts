import * as aws from "@pulumi/aws";

const lifecyclePolicy = JSON.stringify({
    rules: [
        {
            rulePriority: 1,
            description: "Keep last 10 git-tagged images",
            selection: { tagStatus: "tagged", tagPrefixList: ["git-"], countType: "imageCountMoreThan", countNumber: 10 },
            action: { type: "expire" },
        },
        {
            rulePriority: 2,
            description: "Expire untagged images after 1 day",
            selection: { tagStatus: "untagged", countType: "sinceImagePushed", countUnit: "days", countNumber: 1 },
            action: { type: "expire" },
        },
    ],
});

export const backendRepo = new aws.ecr.Repository("parking-lot-backend", {
    name: "parking-lot/backend",
    imageTagMutability: "MUTABLE",
    imageScanningConfiguration: { scanOnPush: true },
    tags: { Name: "parking-lot-backend" },
});

new aws.ecr.LifecyclePolicy("parking-lot-backend-lifecycle", {
    repository: backendRepo.name,
    policy: lifecyclePolicy,
});

export const frontendRepo = new aws.ecr.Repository("parking-lot-frontend", {
    name: "parking-lot/frontend",
    imageTagMutability: "MUTABLE",
    imageScanningConfiguration: { scanOnPush: true },
    tags: { Name: "parking-lot-frontend" },
});

new aws.ecr.LifecyclePolicy("parking-lot-frontend-lifecycle", {
    repository: frontendRepo.name,
    policy: lifecyclePolicy,
});
