import asyncio
from unittest import TestCase
from unittest.mock import MagicMock

import httpx

from app.services.ai.providers.mistral_provider import MistralProvider


class MistralProviderTests(TestCase):
    def test_client_retries_transient_upload_failures(self):
        provider = MistralProvider(
            api_key="test-key",
            request_timeout_sec=45,
            retry_max_elapsed_sec=12,
            logger=MagicMock(),
        )

        config = provider.client.sdk_configuration
        retry = config.retry_config

        self.assertEqual(config.timeout_ms, 45_000)
        self.assertEqual(retry.strategy, "backoff")
        self.assertEqual(retry.backoff.max_elapsed_time, 12_000)
        self.assertTrue(retry.retry_connection_errors)

    def test_transport_errors_are_retryable(self):
        provider = MistralProvider(api_key="test-key", logger=MagicMock())
        request = httpx.Request("POST", "https://api.mistral.ai/v1/files")

        self.assertTrue(
            provider._is_retryable_error(httpx.ConnectError("unavailable", request=request))
        )
        self.assertTrue(provider._is_retryable_error(asyncio.TimeoutError()))

