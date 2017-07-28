######################################################################################################################
#  Copyright 2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Amazon Software License (the "License"). You may not use this file except in compliance        #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://aws.amazon.com/asl/                                                                                    #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################
import json
import os
from datetime import datetime

import actions
import configuration
from actions import *
from boto_retry import get_client_with_retries

BACKUP_OBJECT_KEY_TEMPLATE = "{}ConfigurationBackup-{:0>4d}{:0>2d}{:0>2d}{:0>2d}{:0>2d}{:0>2d}.json"

ERR_ENVIRONMENT_CONFIG_VARIABLE_ = "Configuration table not defined in environment variable {}"

INF_BACKUP = "Backing up configuration table {}"

PARAM_DESC_S3_BUCKET = "Name of S3 bucket to store backup files"
PARAM_DESC_S3_PREFIX = "S3 object prefix for backup files"

PARAM_LABEL_S3_BUCKET = "S3 bucket"
PARAM_LABEL_S3_PREFIX = "S3 object prefix"

PARAM_S3_BUCKET = "S3Bucket"
PARAM_S3_PREFIX = "S3Prefix"


class SchedulerConfigBackupAction:
    """
    Creates backup of scheduler task configuration dynamodb table to S3
    """

    properties = {

        ACTION_TITLE: "Scheduler Config Backup",
        ACTION_VERSION: "1.0",
        ACTION_DESCRIPION: "Creates a daily backup of configuration table",
        ACTION_AUTHOR: "AWS",
        ACTION_ID: "afcfa6ee-ec48-4506-84cb-b4c2bcc9217c",

        ACTION_SERVICE: "time",
        ACTION_RESOURCES: "",
        ACTION_AGGREGATION: ACTION_AGGREGATION_RESOURCE,
        ACTION_MEMORY: 128,
        ACTION_CROSS_ACCOUNT: False,
        ACTION_INTERNAL: True,
        ACTION_MULTI_REGION: False,

        ACTION_PARAMETERS: {

            PARAM_S3_BUCKET: {
                PARAM_LABEL: PARAM_LABEL_S3_BUCKET,
                PARAM_DESCRIPTION: PARAM_DESC_S3_BUCKET,
                PARAM_TYPE: str,
                PARAM_REQUIRED: True,

            },
            PARAM_S3_PREFIX: {
                PARAM_LABEL: PARAM_LABEL_S3_PREFIX,
                PARAM_DESCRIPTION: PARAM_DESC_S3_PREFIX,
                PARAM_TYPE: str,
                PARAM_REQUIRED: True,
                PARAM_MIN_LEN: 1

            }
        },
        ACTION_PERMISSIONS: ["dynamodb:Scan", "s3:PutObject"]
    }

    def __init__(self, arguments):
        self.logger = arguments[actions.ACTION_PARAM_LOGGER]
        self.context = arguments[actions.ACTION_PARAM_CONTEXT]
        self.session = arguments[actions.ACTION_PARAM_SESSION]
        self.config_table = os.getenv(configuration.ENV_CONFIG_TABLE, None)
        self.session = arguments[actions.ACTION_PARAM_SESSION]
        self.debug = arguments.get(actions.ACTION_PARAM_DEBUG, False)

        if self.config_table is None:
            raise Exception(ERR_ENVIRONMENT_CONFIG_VARIABLE_.format(configuration.ENV_CONFIG_TABLE))

        self.S3Bucket = arguments[PARAM_S3_BUCKET]
        self.S3Prefix = arguments[PARAM_S3_PREFIX]

    def execute(self, _):

        self.logger.info("{}, version {}", str(self.__class__).split(".")[-1], self.properties[ACTION_VERSION])
        self.logger.debug("Implementation {}", __name__)

        self.logger.info(INF_BACKUP, self.config_table)

        scan_args = {"TableName": self.config_table}

        backup_config_items = []

        dynamodb_client = get_client_with_retries("dynamodb", ["scan"], context=self.context, session=self.session)

        # get all configuration items
        while True:
            resp = dynamodb_client.scan_with_retries(**scan_args)
            for item in resp.get("Items", []):
                if self.debug:
                    self.logger.debug(json.dumps(item))
                backup_config_items.append(item)

            if "LastEvaluatedKey" in resp:
                scan_args["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
            else:
                break

        s3_client = get_client_with_retries("s3", ["put_object"], context=self.context, session=self.session)

        # create name of object in s3
        dt = datetime.now()
        backup_object_key = BACKUP_OBJECT_KEY_TEMPLATE.format(self.S3Prefix, dt.year, dt.month, dt.day, dt.hour,dt.minute, dt.second)

        backup_data = json.dumps(backup_config_items, indent=3)
        resp = s3_client.put_object_with_retries(Body=backup_data, Bucket=self.S3Bucket, Key=backup_object_key)

        if self.debug:
            self.logger.debug(resp)

        return {
            "backed-up-config-items": len(backup_config_items), "backup-name": backup_object_key, "backup-bucket": self.S3Bucket
        }
