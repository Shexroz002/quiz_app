# Repository Architecture

This file records implemented architecture only. Paths are repository-relative.

## Runtime And Layering

- `app/main.py`: FastAPI composition root. Mounts `/media`, CORS, pagination, `/api/v1` routers, four primary WebSocket routers, the session-monitoring WebSockets, and chat HTTP routes. It also owns the Redis real-time event consumer lifecycle. `GET /` is a health response.
- Request flow is normally endpoint -> service -> repository -> database. FastAPI dependencies construct services and authenticated users.
- PostgreSQL via async SQLAlchemy stores users, quizzes, sessions, groups, notifications, chat metadata, and reactions. MongoDB stores chat message documents. Redis stores presence/live-session state and carries chat/PDF pub-sub events. Celery runs AI/PDF and Telegram room tasks.
- `app/core/database/base.py`: canonical FastAPI `engine`, Celery `celery_engine` with `NullPool`, `AsyncSessionLocal`, `CeleryAsyncSessionLocal`, declarative `Base`, and `get_db`.
- `app/core/database/session.py`: separate lightweight `AsyncSessionLocal`, currently used by `app/websocket/student_session_ws.py` and chat WebSocket code. Do not introduce another session factory.
- `app/core/database/mongodb.py`: Motor client, `get_mongo_db`, `get_mongo_db_to_method`, and `MongoDep`.
- `app/core/database/redis.py`: shared async `redis_client` and `get_redis_client`.

## Relational Models And Relationships

All normal integer-ID entities extend `app/models/base/base_model.py:BaseModel`, which combines `IDMixin` and timezone-aware `TimestampMixin`. `PDFJob` overrides the ID with a UUID.

- `app/models/account/user.py`: `User`; identity, credentials, Telegram/profile/education fields and role. Relations: owns `Quiz`; has `UserSubject`; participates through `SessionParticipant`; creates `StudentGroup`; joins groups through `StudentGroupMember`; participates in directed `Contact` rows.
- `app/models/account/contact.py`: `Contact`; directed `(user_id, friend_id)` relationship to two `User` roles, unique per pair.
- `app/models/account/user_subject.py`: `UserSubject`; join entity from `User` to `Subject`.
- `app/models/science/school_subject.py`: `Subject`; unique subject metadata and reverse `UserSubject` relation.
- `app/models/quiz/quiz.py`: `Quiz`; belongs to optional author `User`, owns cascading `Question` rows, and has `QuizSession` rows.
- `app/models/quiz/question.py`: `Question`; belongs to `Quiz`, owns cascading `Option`, `QuestionImage`, and `AttemptAnswer` rows. `QuestionImage` stores media paths.
- `app/models/quiz/options.py`: `Option`; answer label/text/correctness for one `Question`.
- `app/models/quiz/ai_quiz/pdf_to_quiz.py`: `PDFJob`; queued AI/PDF work owned by a user, optionally linked to `Subject` and generated `Quiz`, with progress, Celery ID, result, and error fields.
- `app/models/quiz/real_time_quiz/quiz_session.py`: `QuizSession`; quiz run hosted by `User`, with join code, status/type, capacity, actual `started_at`/`finished_at`, and `deadline_at`. Owns participants, attempts, and `QuizSessionGroup` links.
- `app/models/quiz/real_time_quiz/session_participant.py`: `SessionParticipant`; session/user participation row with nickname, host flag, joined time, and participant status; belongs to `QuizSession` and `User`.
- `app/models/quiz/real_time_quiz/quiz_attempt.py`: `QuizAttempt`; one unique participant attempt per session, with scored state and cascading `AttemptAnswer` rows.
- `app/models/quiz/real_time_quiz/attempt_answer.py`: `AttemptAnswer`; selected option and correctness for an attempt/question; unique and indexed on `(attempt_id, question_id)`.
- `app/models/group/student_group.py`: `StudentGroup` owned by a teacher, optionally tied to `Subject`; owns `StudentGroupMember` and `QuizSessionGroup` links. `StudentGroupMember` joins a student to a group and tracks the adding user.
- `app/models/quiz/real_time_quiz/quiz_group.py`: `QuizSessionGroup`; unique session/group join entity between `QuizSession` and `StudentGroup`.
- `app/models/notification/notification.py`: `Notification`; recipient/sender users, typed action, JSON payload, read and soft-delete state.
- `app/models/chat/chats.py`: `Chat`; relational chat metadata, owner, direct-chat key, cached last-message fields, and `ChatMember` collection.
- `app/models/chat/chat_members.py`: `ChatMember`; unique chat/user membership, role, join time, and Mongo message read cursor.
- `app/models/message/message_reaction.py`: `MessageReaction`; relational reaction record keyed by chat/message/user. Mongo message documents also carry reaction data through `MessageRepository`.
- `app/bot/models.py`: `TelegramQuizRoom` durably maps a managed `QuizSession` to one Telegram chat message and leaderboard delivery state. `TelegramSinglePlayerResultDelivery` is the private-chat outbox keyed uniquely by a finished `QuizAttempt`.
- `app/models/__init__.py` and package `__init__.py` files expose commonly imported models. `migration/env.py` imports account, quiz, group, and chat model packages for Alembic metadata.

## Domain Enums

- `app/models/account/user.py`: `UserType`, `GenderType`, `EducationLevel`.
- `app/models/quiz/quiz.py`: `QuizGenerateType` (`AI_GENERATE`, `PDF`, `MANUAL`, `UNDEFINED`).
- `app/models/quiz/ai_quiz/pdf_to_quiz.py`: `PDFJobStatus`.
- `app/models/quiz/real_time_quiz/quiz_session.py`: `SessionType`, `SessionStatus`.
- `app/models/quiz/real_time_quiz/session_participant.py`: `ParticipantStatus`.
- `app/models/group/student_group.py`: `GroupColor`, `GroupStatus`.
- `app/models/chat/chats.py`: `ChatType`; `app/models/chat/chat_members.py`: `ChatMemberRole`.
- `app/models/notification/notification.py`: `NotificationType`, `NotificationActionType`.
- `app/schemas/account/users/users.py`: response/filter `StudentStatus`.
- `app/schemas/sessions/session_monitoring.py` and `app/schemas/quiz/session_monitoring.py`: transport `ParticipantLiveStatus` and `ConnectionStatus`; the Redis service uses the `sessions` version while snapshot output uses the `quiz` version.
- `app/websocket/chat/utils/event_type.py`: `EventType` for chat/presence WebSocket messages.

## Repositories And Data Access

- `app/repositories/base/base_repository.py:BaseRepository`: generic SQLAlchemy `get`, `list`, `create`, `update`, `delete`.
- `app/repositories/account/user_repo.py:UserRepository`: username/conflict lookups, contact-aware user search, full user data, and profile updates.
- `app/repositories/account/user_subject_repo.py:UserSubjectRepository`: bulk create and replacement/update of user-subject links.
- `app/repositories/account/contact_repo.py:ContactRepository`: contacts/suggestions plus teacher-student list, cards, weak topics, subject stats, history, and leaderboard aggregate queries.
- `app/repositories/subject/subject_repo.py:SubjectRepository`: generic subject access.
- `app/repositories/quiz/quiz_repo.py:QuizRepository`: quiz CRUD/detail, question counts and answers, student topic/subject/overall analytics, teacher quiz list/statistics, and correct-option completeness checks.
- `app/repositories/quiz/question_repo.py:QuestionRepository`: owner-scoped question detail/list/update, session-safe question lists, image attach/delete, and correct-option updates.
- `app/repositories/quiz/quiz_session_repo.py:QuizSessionRepository`: session create/start/finish/lookups; single-player and multiplayer fetches; questions/results/rankings/history; group authorization; teacher dashboards, charts, group results, weak-topic and weak-student analytics.
- `app/repositories/quiz/session_participant.py:SessionParticipantRepository`: participant create/lookups/listing and disconnect state.
- `app/repositories/quiz/quiz_attempt_repo.py:QuizAttemptRepository`: attempt get/create, answer upsert and validation, counts, topic stats, and question order.
- `app/repositories/quiz/pdf_job_repo.py:PDFJobRepository`: create/get job, attach Celery task ID, and update job status/result fields.
- `app/repositories/group/student_group_repository.py:StudentGroupRepository`: group/member mutation and validation; teacher/member list views; detail, performance, test-result, and student-ID aggregate queries.
- `app/repositories/notification/notification_repo.py:NotificationRepo`: create/list/count notifications and mark one/all read.
- `app/repositories/chat/chat_repo.py:ChatRepository`: SQL chat/member CRUD, membership/read cursors, cached last message, and member detail with Redis presence.
- `app/repositories/chat/message_repo.py:MessageRepository`: Mongo `messages` collection create/forward/history/edit/soft-delete/reactions/views/read flags, last message, and unread counts.
- `app/repositories/chat/presence_repository.py:PresenceRepository`: Redis online and last-seen single/bulk reads.

## Services And Business Logic

- `app/services/base/base_service.py:BaseService`: generic service delegation around `BaseRepository`.
- `app/services/account/auth_service.py:AuthService`: login, JWT refresh, registration with subjects, and full-user lookup; reuses `UserRepository`, `UserSubjectRepository`, password helpers, and JWT helpers.
- `app/services/account/users.py:UserService`: self-update, subject replacement, avatar storage, user lookup/search; reuses `StorageService` even for images.
- `app/services/account/contact_service.py:ContactService`: contact creation and all teacher-student authorization/analytics orchestration over `ContactRepository`.
- `app/services/subject/subject_service.py:SubjectService`: generic subject listing/access.
- `app/services/group/student_group_service.py:StudentGroupService`: teacher-owned group/member/image mutations and teacher/student group views; membership checks delegate to `StudentGroupRepository`.
- `app/services/notification/notification_service.py:NotificationService`: persistence plus immediate delivery through `notification_manager`; creates group quiz invitations.
- `app/services/quiz/quiz_service.py:QuizService`: quiz CRUD/list/detail/statistics/recommendations. `save_quiz_from_json` is the shared AI-result persistence path that creates a quiz, questions, options, and mapped images.
- `app/services/quiz/question_service.py:QuestionService`: owner-authorized question editing, correct option mutation, and question image storage/deletion.
- `app/services/quiz/quiz_session.py:QuizSessionService`: main session orchestration. It creates public/group/single-player sessions, joins participants, starts sessions, persists answers, updates Redis monitoring state, builds results/topic stats, manages participant question position, and delegates history/teacher/student analytics to repositories. `finalize_session` is the row-locked, idempotent owner for multiplayer all-finished, deadline, and host finalization, leaderboard calculation, and competition notifications.
- `app/services/redis_service/session_live.py:SessionLiveStateService`: Redis participant JSON state, set membership and TTL; online/offline/heartbeat, answer progress, and current-question updates.
- `app/services/quiz/session_monitoring_service.py:SessionMonitoringService`: builds monitoring snapshots from `SessionLiveStateService`.
- `app/services/chat/chat_service.py:ChatService`: group/private chat creation, membership, list/detail assembly across SQL metadata, Mongo messages, and Redis presence. `_make_direct_key` is the canonical private-chat key helper.
- `app/services/chat/message_service.py:MessageService`: HTTP-facing Mongo message validation and CRUD/reaction/read/view operations.
- `app/services/chat/real_time_event_service.py:RealTimeEventService`: WebSocket event business logic; mutates Mongo/SQL, updates chat previews/read cursors, creates direct chats, and publishes Redis events.
- `app/services/ai/base.py`: provider contract and `AIQuizParseRequest`/`AIQuizParseResult` dataclasses.
- `app/services/ai/ai_service.py:AIQuizParser`: provider-agnostic PDF and description orchestration returning structured quiz data plus image maps.
- `app/services/ai/providers/provider_factory.py:get_provider`: configured provider factory; currently returns Gemini or Mistral. OpenAI is not enabled in the factory.
- `app/services/ai/providers/gemini_provider.py:GeminiProvider`: Gemini file upload/poll/generation, structured JSON parsing, retries, progress, cleanup, and description generation.
- `app/services/ai/providers/mistral_provider.py:MistralProvider`: Mistral upload/OCR structured annotation, image-map extraction, retries, progress, and cleanup.
- `app/services/ai/providers/openai_provider.py:OpenAIProvider`: placeholder provider returning empty data; do not treat it as a working pipeline.
- `app/services/ai/promt.py`: canonical quiz prompts and JSON schemas; `ai_generator_by_description` builds description prompts.
- `app/services/ai/ai_report_generation.py:report_generation`: deterministic recommendation text from subject statistics; despite its path, it does not call an AI provider.
- `app/services/pdf/storage_service.py:StorageService`: chunked size-limited async file persistence; shared by PDF, avatar, and Telegram uploads.
- `app/services/pdf/pdf_service.py:PDFService`: PyMuPDF/Pillow image extraction, test-PDF heuristic, hashing, and base64 image-map persistence.
- `app/services/pdf/pdf_job_service.py:PDFJobService`: validates/stores uploads, creates `PDFJob`, and queues PDF or description tasks.
- `app/services/pdf/redis_pubsub_service.py`: commits job status and publishes `pdf_job:{job_id}` events.

## Background Tasks And AI/PDF Flow

- `app/core/celery_app.py`: Celery app, Redis broker/backend config, PDF/AI and quiz-session queues. It autodiscovers PDF tasks and schedules expired running-session recovery every 60 seconds.
- `app/services/quiz/tasks/session_tasks.py`: deadline ETA finalization task and Celery Beat recovery scan; both delegate to `QuizSessionService.finalize_session` using `CeleryAsyncSessionLocal`.
- `app/services/pdf/tasks/quiz_tasks.py:AIQuizTaskService`: owns task-side job loading, progress callbacks, provider/parser construction, shared quiz persistence, completion, and input cleanup.
- `process_pdf_task`: Mistral OCR -> `AIQuizParser` -> `save_quiz_from_json`; runs on `pdf_ai_queue` using `CeleryAsyncSessionLocal`.
- `generate_quiz_from_description_task`: Gemini generation -> `AIQuizParser` -> `save_quiz_from_json`; runs on `ai_test_generator`.
- `app/bot/tasks.py`: defines Celery `telegram.recover_rooms`, retrying `telegram.maintain_room`, and `telegram.deliver_single_player_result`; recovers durable Telegram room and single-player result outboxes, invokes managed multiplayer finalization, and publishes Telegram messages.
- Flow: `POST /api/v1/quiz-generator/pdf-jobs` or `/quiz/generate` -> `PDFJobService` -> Celery task -> AI provider -> `save_quiz_from_json` -> SQL job completion -> Redis progress -> WebSocket/Telegram watcher.

## HTTP API And Controllers

`app/api/v1/router.py` mounts common routes at `/api/v1`, student routes at `/api/v1/student`, and teacher routes at `/api/v1/teacher`. The files below are controllers and should remain thin.

- `app/api/v1/common/auth/endpoints/auth.py` under `/api/v1/auth`: `POST /me/` login, `POST /refresh/`, `GET /me/`, `POST /register/`.
- `app/api/v1/common/users/endpoints/users.py` under `/api/v1/users`: user get/update/avatar and `/search`.
- `app/api/v1/common/users/endpoints/contact.py` under `/api/v1/users/contact`: create/list/suggest contacts.
- `app/api/v1/common/subject/endpoint/subject.py` under `/api/v1/subject`: subject list.
- `app/api/v1/common/question/endpoints/question.py` under `/api/v1/question`: detail/edit, image upload/delete, and correct-option update.
- `app/api/v1/common/notification/endpoint/notification.py` under `/api/v1/notifications`: list, mark one read, mark all read.
- `app/api/v1/common/quiz_generator/endpoints/ai_quiz.py` under `/api/v1/quiz-generator`: create PDF job, generate from description, and job status.
- `app/api/v1/student/quiz/endpoints/quiz.py` under `/api/v1/student/quizzes`: quiz list/detail/update/delete and topic/subject/recommendation/overall analytics.
- `app/api/v1/student/quiz/endpoints/quiz_sesstion.py` under `/api/v1/student/sessions`: public multiplayer create/join/leave/info/participants/start/questions/answer/question-order/invite/finish/results/topic stats; single-player start/info/finish/error analysis/history/leaderboard.
- `app/api/v1/student/group/endpoints/student_group.py` under `/api/v1/student/group`: member-authorized group list/detail/performance/sessions plus session results, accuracy, and leaderboard.
- `app/api/v1/teacher/my_student/endpoints/students.py` under `/api/v1/teacher/my/student`: student list/search/suggestions/add, student card/weak topics/subject stats/history, and leaderboard.
- `app/api/v1/teacher/group/endpoints/student_group.py` under `/api/v1/teacher/group`: group create/update/image/member mutations and teacher group list/detail/performance/session views.
- `app/api/v1/teacher/quiz/endpoints/quiz.py` under `/api/v1/teacher/quizzes`: teacher quiz list/statistics/detail/delete/update.
- `app/api/v1/teacher/quiz_session/endpoints/group_quiz_live.py` under `/api/v1/teacher/quiz-sessions/live`: group-session create/host finish/running list/results/detail/accuracy/leaderboard/info/participants/start/questions/monitoring.
- `app/api/v1/teacher/statistics/endpoints/card.py` under `/api/v1/teacher/statistic`: dashboard cards, activity chart, analytics overview, group results, weak topics, and weak students.
- `app/api/v1/common/chat/endpoints/chat.py` and `message.py`: mounted by `app/main.py` directly at `/chats` and `/messages`, not under `/api/v1`; chat CRUD/list/detail and Mongo message CRUD/history/reactions/read/view/file upload.
- `app/bot/handlers/webapp.py`: mounted directly by `app/main.py` at `/api/v1/bot`; authenticates Telegram init-data and exposes thin managed-room state/questions/answer/finish endpoints plus the single-player result handoff endpoint.

## Schemas And DTOs

- `app/schemas/account/auth/login.py`: login, token, refresh, login response. `register.py`: registration and password serialization.
- `app/schemas/account/users/users.py`: user list/contact/detail/update/subject DTOs, student table row and status. `contact.py`: contact, student card, weak-topic, subject-stat, history leaderboard/filter DTOs.
- `app/schemas/subject/subject.py`: subject ID and list DTOs.
- `app/schemas/quiz/quiz.py`: student/teacher quiz list/detail/update/statistics and topic/subject/overall analytics DTOs.
- `app/schemas/quiz/question.py` and `options.py`: question/image/detail/edit DTOs, with correct-answer and hidden-correct-answer option variants.
- `app/schemas/quiz/quiz_session.py`: session creation, group validation, teacher/player session responses, question payloads, error analysis, leaderboard, results detail, accuracy, and teacher dashboard DTOs.
- `app/schemas/quiz/quiz_attempt.py`: answer submission/order, finish/topic result, and participant-attempt DTOs.
- `app/schemas/quiz/session_participant.py`: participant creation/list and minimal session detail.
- `app/schemas/sessions/session_monitoring.py`: Redis/live participant state, table response, event, and live quiz card. `app/schemas/quiz/session_monitoring.py`: API snapshot/event counterpart used by monitoring service.
- `app/schemas/quiz/quiz_live.py`: alternate basic live-session command DTOs; no current imports were found. Prefer the actively used `quiz_session.py` and `quiz_attempt.py` types before extending this file.
- `app/schemas/group/student_group.py`: create/update, cards/detail, member rows, performance, cover image, and test result DTOs.
- `app/schemas/chat/chat_schema.py`, `chat_list.py`, `message_schema.py`: chat creation/response/list/detail/member and Mongo message/attachment/reaction/read DTOs.
- `app/schemas/notification/notification.py`: notification sender/create/response/read DTOs.
- `app/schemas/statistic/teacher_dashboard.py` and `teacher_statistics.py`: activity chart, overview cards, group performance, weak topics/students and filters.
- `app/api/v1/teacher/quiz/params/quiz_filter.py` and `app/api/v1/teacher/my_student/params/student_filter.py`: FastAPI query/filter DTOs.

## WebSockets And Real-Time State

- `app/websocket/utils/auth_ws.py:authenticate_websocket`: shared query-token JWT authentication and SQL user lookup.
- `app/websocket/manager.py:SessionConnectionManager`: active manager for `/ws/quiz/sessions/{session_id}`; emits `{event, data}`.
- `app/websocket/exam_ws.py`: authorized quiz-session connection, participant READY transition, ping/pong, and session chat broadcast.
- `app/websocket/session_monitoring_ws_manager.py:SessionMonitoringWSManager`: host/participant monitoring connections; emits `{event, payload}`.
- `app/websocket/student_session_ws.py`: `/ws/quiz-sessions/{session_id}` host heartbeat and `/participant` presence heartbeat; reuses `SessionLiveStateService` and broadcasts monitoring updates.
- `app/websocket/notification_manager.py:NotificationConnectionManager` and `notification_ws.py`: authenticated per-user sockets and service-driven notification/count delivery.
- `app/services/redis_service/realtime_events.py` and `app/websocket/redis_events.py`: Redis pub/sub bridge for worker-originated notification and quiz-session events to FastAPI-owned WebSocket managers.
- `app/websocket/pdf_job_ws.py`: owner-authorized job snapshot plus Redis `pdf_job:{job_id}` stream until completed/failed.
- `app/websocket/chat/chat_websocket.py`: `/ws/chat`; subscribes to chat, friend-presence and user Redis channels, manages presence, and runs two directional tasks.
- `app/websocket/chat/utils/chat_ws.py`: Redis-to-client envelope conversion and client-to-`RealTimeEventService` dispatch. `presence.py` owns TTL/last-seen helpers and SQL chat/contact channel discovery.
- `app/websocket/chat/chat_ws_manager.py`: in-process multi-device connection registry. `app/repositories/chat/presence_repository.py` provides read-only Redis presence access.
- `app/core/websocket/websocket_manager.py` is a separate generic manager with no imports found. Extend the active managers above before considering it.

## Telegram Bot And Mini App

- `app/bot/main.py`: aiogram polling composition; includes start, menu, quiz, and quiz-room routers.
- `app/bot/handlers/start.py`: `/start`, durable room deep-link entry including post-registration continuation, phone contact registration, grade selection, profile-photo import, and main menu.
- `app/bot/handlers/menu.py`: owner-scoped quiz catalog pagination/cards, user-scoped completed-attempt result history and Telegram pagination, catalog-message cleanup on selection, PDF generation entry, single-player Mini App launch, managed-room creation, and menu callbacks. The shared catalog renderer emits separate `single:*` and `friends:*` pagination/card/duration namespaces; only the friends handlers call the managed-room transport.
- `app/bot/handlers/quiz_room.py`: thin owner-start and room-refresh callbacks over the managed multiplayer service and durable room publisher.
- `app/bot/handlers/quiz.py`: PDF download/adaptation to `UploadFile`, `PDFJobService` creation, Redis progress watcher, and generated-quiz open/start callbacks.
- `app/bot/services/quiz_room.py`: Telegram transport for durable managed rooms. It reuses `MultiplayerQuizService`; owns duration parsing, registered-user checks, room creation/deduplication, full-name participant room-state message edits, room entry, participant-private Mini App start links, and full-name leaderboard formatting. Final leaderboards are sent as separate Telegram messages and guarded by durable delivery state.
- `app/bot/services/single_player_result.py`: durable private-chat single-player result handoff, formatting, queueing, and delivery. It reads authoritative finished-attempt results through `QuizSessionService` and never accepts result fields from the Mini App.
- `app/bot/utils/registration.py`: Telegram-ID lookup and phone-linked/new student registration using `UserRepository`, existing enums, hashing, and shared SQL sessions.
- `app/bot/utils/progress.py`: Redis job-to-message mapping, PDF job snapshots, progress text/message edits, and async watcher lifecycle.
- `app/bot/utils/profile_photo.py` and `upload.py`: `StorageService`-compatible Telegram file adapters.
- `app/bot/keyboards/reply.py`: phone contact and persistent main-menu keyboards. `inline.py`: registration, catalog, duration, and WebApp keyboards and URL. `quiz_room.py`: waiting-room join deep links plus direct Mini App buttons for running rooms.
- `app/bot/states/__init__.py`: registration, PDF generation, and custom-duration FSM states.
- `app/bot/webapp`: Vite/React Telegram Mini App. `src/pages/QuizPage.jsx` owns quiz UI/state and switches between existing single-player and managed-room flows; `src/api/quiz.js` authenticates and calls the corresponding APIs; `src/utils/telegram.js` reads and validates Telegram init/query data. `src/components/RichText.jsx`, `Question.jsx`, `QuestionMedia.jsx`, `AnswerOptions.jsx`, `QuizProgress.jsx`, and `QuizTimer.jsx` own Markdown/KaTeX rendering, media, choices, progress, and deadline UI.

## Shared Utilities, Security, And Configuration

- `app/core/config.py:Settings`: `.env`-backed database/timezone, Redis/Celery, JWT, media limits/paths, Gemini/Mistral/OpenAI/DeepSeek, MongoDB, base URL, and Telegram settings.
- `app/core/security/jwt.py`: access/refresh creation and decoding. `password_hash.py`: shared `pwdlib` hashing/verification. `app/api/v1/common/auth/dependencies/current_user.py`: OAuth2 bearer-to-user dependency.
- `app/utils/datetime.py`: canonical UTC/Tashkent-aware now/conversion/day/week helpers. Use these instead of naive datetimes.
- `app/services/pdf/pdf_service.py` is the implemented PDF/image utility. The similarly named `app/services/pdf_service.py`, `app/utils/pdf_utils.py`, `app/utils/latex_utils.py`, `app/utils/timer.py`, `app/services/session_service.py`, `app/workers/pdf_tasks.py`, `app/workers/celery_app.py`, `app/api/v1/common/chat/endpoints/file_upload.py`, and `app/schemas/quiz/test.py` are empty placeholders. `app/bot/handlers/profile.py` and `app/bot/middlewares/auth.py` contain no behavior.
- `migration/versions/20260905_0001_timezone_aware_timestamps.py`: timezone-aware timestamp migration.
- `migration/versions/20260908_0002_quiz_session_deadline.py`: adds `QuizSession.deadline_at`, migrates running-session deadlines, and removes the default finish timestamp from unfinished attempts.
- `migration/versions/20260909_0003_telegram_quiz_rooms.py`: creates the durable `telegram_quiz_rooms` table, constraints, foreign key, and timestamp indexes used by managed Telegram multiplayer rooms.
- `migration/versions/20260909_0004_telegram_single_player_results.py`: creates the attempt-unique durable outbox for private Telegram single-player result delivery.
- `docker-compose-local.yml`: Postgres, Redis, Mongo, FastAPI, Celery, aiogram bot, Vite WebApp, and Cloudflare tunnel. `docker/dev/run-cloudflared.sh` restarts the local accountless quick tunnel when Cloudflare invalidates its tunnel ID. `docker-compose.yml`: production Postgres/Redis/API/Celery topology. `requirements.txt` and `app/bot/webapp/package.json` are dependency manifests.

## Reuse Map

- New SQL CRUD: extend the nearest repository/service; reuse `BaseRepository`/`BaseService` only where the domain has no specialized owner.
- New quiz/session behavior: extend `QuizSessionService`; shared-deadline finalization belongs in its central `finalize_session` method, and persistence queries belong in the existing quiz repositories.
- New AI provider behavior: implement `AIProvider`, register it in `get_provider`, and keep parsing/orchestration in `AIQuizParser`/`AIQuizTaskService`.
- New generated quiz source: feed the existing `save_quiz_from_json` path and `PDFJob` progress lifecycle.
- New job progress consumer: subscribe to existing `pdf_job:{job_id}` events; do not create another status store.
- New chat operation: reuse SQL `ChatRepository`, Mongo `MessageRepository`, and `RealTimeEventService`; use `EventType` and existing Redis channels.
- New live monitoring field/event: extend `ParticipantLiveStateSchema`, `SessionLiveStateService`, snapshot service, and monitoring manager together.
- New notifications: use `NotificationService.create_notification` so SQL persistence, unread count, and WebSocket delivery remain coupled.
- New Telegram quiz behavior: keep Telegram transport in `app/bot`, but reuse core quiz/session services and shared models rather than duplicating scoring or lifecycle logic.
- New media persistence: reuse `StorageService` and configured directories; URL serialization already exists in multiple response schemas via `settings.BASE_URL`.

## Observed Wiring Gaps

These are current repository facts, not proposed architecture. Fix the existing owners when relevant; do not route around them with parallel implementations.

- `migration/env.py` imports only the symbols exported by account/quiz packages plus group, chat, and `TelegramQuizRoom`. Its target metadata still omits some existing models such as `Contact`, `UserSubject`, `Notification`, and `MessageReaction`.
- `app/tests` has focused managed multiplayer finalization and leaderboard tests, but no broad integration suite for the existing application.
