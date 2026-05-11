import * as aws from "@pulumi/aws";
import * as pulumi from "@pulumi/pulumi";
import { cluster } from "./cluster";
import { taskExecutionRole } from "./iam";
import { backendRepo, frontendRepo } from "./ecr";
import { secretKeySecret, dbPasswordSecret, rabbitmqUserSecret, rabbitmqPassSecret, googleMapsSecret } from "./secrets";
import { corsOrigins } from "./config";

const region = aws.getRegionOutput().name;
const accountId = aws.getCallerIdentityOutput().accountId;

// Helper: create a CloudWatch log group and return its name
const makeLogGroup = (name: string) =>
    new aws.cloudwatch.LogGroup(`parking-lot-logs-${name}`, {
        name: `/ecs/parking-lot/${name}`,
        retentionInDays: 7,
    });

const dbLogs       = makeLogGroup("db");
const rabbitmqLogs = makeLogGroup("rabbitmq");
const backendLogs  = makeLogGroup("backend");
const workerLogs   = makeLogGroup("worker");
const frontendLogs = makeLogGroup("frontend");

// Shared secret refs for task definitions
const secretRefs = (domain: string) => [
    { name: "SECRET_KEY",           valueFrom: secretKeySecret.arn },
    { name: "DB_PASSWORD",          valueFrom: dbPasswordSecret.arn },
    { name: "RABBITMQ_USER",        valueFrom: rabbitmqUserSecret.arn },
    { name: "RABBITMQ_PASS",        valueFrom: rabbitmqPassSecret.arn },
    { name: "GOOGLE_MAPS_API_KEY",  valueFrom: googleMapsSecret.arn },
];

// --- db ---
const dbTaskDef = new aws.ecs.TaskDefinition("parking-lot-db-task", {
    family: "parking-lot-db",
    networkMode: "host",
    executionRoleArn: taskExecutionRole.arn,
    containerDefinitions: JSON.stringify([{
        name: "db",
        image: "postgis/postgis:15-3.3",
        essential: true,
        environment: [
            { name: "POSTGRES_USER",     value: "postgres" },
            { name: "POSTGRES_DB",       value: "parking_lots" },
        ],
        secrets: [{ name: "POSTGRES_PASSWORD", valueFrom: dbPasswordSecret.arn }],
        mountPoints: [{ sourceVolume: "postgres-data", containerPath: "/var/lib/postgresql/data" }],
        logConfiguration: {
            logDriver: "awslogs",
            options: { "awslogs-group": dbLogs.name, "awslogs-region": region, "awslogs-stream-prefix": "db" },
        },
    }]),
    volumes: [{ name: "postgres-data" }],
    tags: { Name: "parking-lot-db" },
});

new aws.ecs.Service("parking-lot-db-service", {
    cluster: cluster.arn,
    taskDefinition: dbTaskDef.arn,
    desiredCount: 1,
    tags: { Name: "parking-lot-db" },
});

// --- rabbitmq ---
const rabbitmqTaskDef = new aws.ecs.TaskDefinition("parking-lot-rabbitmq-task", {
    family: "parking-lot-rabbitmq",
    networkMode: "host",
    executionRoleArn: taskExecutionRole.arn,
    containerDefinitions: pulumi.all([rabbitmqUserSecret.arn, rabbitmqPassSecret.arn]).apply(([userArn, passArn]) =>
        JSON.stringify([{
            name: "rabbitmq",
            image: "rabbitmq:3.13-management",
            essential: true,
            command: ["sh", "-c", "rabbitmq-plugins enable rabbitmq_stream rabbitmq_stream_management && rabbitmq-server"],
            secrets: [
                { name: "RABBITMQ_DEFAULT_USER", valueFrom: userArn },
                { name: "RABBITMQ_DEFAULT_PASS", valueFrom: passArn },
            ],
            logConfiguration: {
                logDriver: "awslogs",
                options: { "awslogs-group": "/ecs/parking-lot/rabbitmq", "awslogs-region": "us-east-1", "awslogs-stream-prefix": "rabbitmq" },
            },
        }])
    ),
    tags: { Name: "parking-lot-rabbitmq" },
});

new aws.ecs.Service("parking-lot-rabbitmq-service", {
    cluster: cluster.arn,
    taskDefinition: rabbitmqTaskDef.arn,
    desiredCount: 1,
    tags: { Name: "parking-lot-rabbitmq" },
});

// --- backend ---
const backendTaskDef = new aws.ecs.TaskDefinition("parking-lot-backend-task", {
    family: "parking-lot-backend",
    networkMode: "host",
    executionRoleArn: taskExecutionRole.arn,
    containerDefinitions: pulumi.all([
        backendRepo.repositoryUrl,
        secretKeySecret.arn,
        dbPasswordSecret.arn,
        rabbitmqUserSecret.arn,
        rabbitmqPassSecret.arn,
        googleMapsSecret.arn,
    ]).apply(([repoUrl, skArn, dbArn, rmqUserArn, rmqPassArn, gmArn]) =>
        JSON.stringify([{
            name: "backend",
            image: `${repoUrl}:latest`,
            essential: true,
            command: ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"],
            environment: [
                { name: "DATABASE_URL",   value: "postgresql://postgres:$(DB_PASSWORD)@localhost:5432/parking_lots" },
                { name: "RABBITMQ_URL",   value: "amqp://$(RABBITMQ_USER):$(RABBITMQ_PASS)@localhost:5672/" },
                { name: "CORS_ORIGINS",   value: corsOrigins },
                { name: "HF_HOME",        value: "/app/.cache/huggingface" },
            ],
            secrets: [
                { name: "SECRET_KEY",          valueFrom: skArn },
                { name: "DB_PASSWORD",         valueFrom: dbArn },
                { name: "RABBITMQ_USER",       valueFrom: rmqUserArn },
                { name: "RABBITMQ_PASS",       valueFrom: rmqPassArn },
                { name: "GOOGLE_MAPS_API_KEY", valueFrom: gmArn },
            ],
            mountPoints: [{ sourceVolume: "hf-cache", containerPath: "/app/.cache/huggingface" }],
            logConfiguration: {
                logDriver: "awslogs",
                options: { "awslogs-group": "/ecs/parking-lot/backend", "awslogs-region": "us-east-1", "awslogs-stream-prefix": "backend" },
            },
        }])
    ),
    volumes: [{ name: "hf-cache" }],
    tags: { Name: "parking-lot-backend" },
});

new aws.ecs.Service("parking-lot-backend-service", {
    cluster: cluster.arn,
    taskDefinition: backendTaskDef.arn,
    desiredCount: 1,
    tags: { Name: "parking-lot-backend" },
});

// --- worker ---
const workerTaskDef = new aws.ecs.TaskDefinition("parking-lot-worker-task", {
    family: "parking-lot-worker",
    networkMode: "host",
    executionRoleArn: taskExecutionRole.arn,
    containerDefinitions: pulumi.all([
        backendRepo.repositoryUrl,
        dbPasswordSecret.arn,
        rabbitmqUserSecret.arn,
        rabbitmqPassSecret.arn,
        googleMapsSecret.arn,
    ]).apply(([repoUrl, dbArn, rmqUserArn, rmqPassArn, gmArn]) =>
        JSON.stringify([{
            name: "worker",
            image: `${repoUrl}:latest`,
            essential: true,
            command: ["python", "-m", "app.worker_main"],
            environment: [
                { name: "DATABASE_URL", value: "postgresql://postgres:$(DB_PASSWORD)@localhost:5432/parking_lots" },
                { name: "RABBITMQ_URL", value: "amqp://$(RABBITMQ_USER):$(RABBITMQ_PASS)@localhost:5672/" },
                { name: "HF_HOME",      value: "/app/.cache/huggingface" },
            ],
            secrets: [
                { name: "DB_PASSWORD",         valueFrom: dbArn },
                { name: "RABBITMQ_USER",       valueFrom: rmqUserArn },
                { name: "RABBITMQ_PASS",       valueFrom: rmqPassArn },
                { name: "GOOGLE_MAPS_API_KEY", valueFrom: gmArn },
            ],
            mountPoints: [
                { sourceVolume: "hf-cache",   containerPath: "/app/.cache/huggingface" },
                { sourceVolume: "model",       containerPath: "/app/model", readOnly: true },
            ],
            logConfiguration: {
                logDriver: "awslogs",
                options: { "awslogs-group": "/ecs/parking-lot/worker", "awslogs-region": "us-east-1", "awslogs-stream-prefix": "worker" },
            },
        }])
    ),
    volumes: [
        { name: "hf-cache" },
        { name: "model" },
    ],
    tags: { Name: "parking-lot-worker" },
});

new aws.ecs.Service("parking-lot-worker-service", {
    cluster: cluster.arn,
    taskDefinition: workerTaskDef.arn,
    desiredCount: 1,
    tags: { Name: "parking-lot-worker" },
});

// --- frontend ---
const frontendTaskDef = new aws.ecs.TaskDefinition("parking-lot-frontend-task", {
    family: "parking-lot-frontend",
    networkMode: "host",
    executionRoleArn: taskExecutionRole.arn,
    containerDefinitions: frontendRepo.repositoryUrl.apply(repoUrl =>
        JSON.stringify([{
            name: "frontend",
            image: `${repoUrl}:latest`,
            essential: true,
            logConfiguration: {
                logDriver: "awslogs",
                options: { "awslogs-group": "/ecs/parking-lot/frontend", "awslogs-region": "us-east-1", "awslogs-stream-prefix": "frontend" },
            },
        }])
    ),
    tags: { Name: "parking-lot-frontend" },
});

new aws.ecs.Service("parking-lot-frontend-service", {
    cluster: cluster.arn,
    taskDefinition: frontendTaskDef.arn,
    desiredCount: 1,
    tags: { Name: "parking-lot-frontend" },
});
