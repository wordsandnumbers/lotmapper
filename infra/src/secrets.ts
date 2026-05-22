import * as aws from "@pulumi/aws";
import * as pulumi from "@pulumi/pulumi";
import { secretKey, dbPassword, rabbitmqUser, rabbitmqPass, googleMapsApiKey, corsOrigins } from "./config";

const makeSecret = (name: string, value: pulumi.Input<string>) =>
    new aws.secretsmanager.Secret(`parking-lot-${name}`, {
        name: `parking-lot/${name}`,
        tags: { Name: `parking-lot/${name}` },
    });

const makeSecretVersion = (secret: aws.secretsmanager.Secret, value: pulumi.Input<string>) =>
    new aws.secretsmanager.SecretVersion(`${secret.name}-version`, {
        secretId: secret.id,
        secretString: value,
    });

export const secretKeySecret     = makeSecret("secret-key", secretKey);
export const dbPasswordSecret    = makeSecret("db-password", dbPassword);
export const rabbitmqUserSecret  = makeSecret("rabbitmq-user", rabbitmqUser);
export const rabbitmqPassSecret  = makeSecret("rabbitmq-pass", rabbitmqPass);
export const googleMapsSecret    = makeSecret("google-maps-api-key", googleMapsApiKey);

makeSecretVersion(secretKeySecret, secretKey);
makeSecretVersion(dbPasswordSecret, dbPassword);
makeSecretVersion(rabbitmqUserSecret, rabbitmqUser);
makeSecretVersion(rabbitmqPassSecret, rabbitmqPass);
makeSecretVersion(googleMapsSecret, googleMapsApiKey);
