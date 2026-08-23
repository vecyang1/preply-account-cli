"""Operations that are not specific to one side of a tutoring."""

from __future__ import annotations

from ._operation import GraphQLOperation

OPERATIONS: dict[str, GraphQLOperation] = {
    "PreplyCliAccountIdentity": GraphQLOperation(
        "PreplyCliAccountIdentity",
        """
        query PreplyCliAccountIdentity {
            currentUser {
                id
                firstName
                fullName
                tutor {
                    id
                }
                profile {
                    id
                    currency {
                        id
                        code
                    }
                    timezone {
                        id
                        tzname
                    }
                }
                wallet {
                    id
                    balance
                }
            }
        }
        """,
    ),
    "Timezone": GraphQLOperation(
        "Timezone",
        """
        query Timezone {
            currentUser {
                id
                profile {
                    id
                    timezone {
                        id
                        tzname
                        tzOffset
                    }
                }
            }
        }
        """,
    ),
    "ChatThreadSummaries": GraphQLOperation(
        "ChatThreadSummaries",
        """
        query ChatThreadSummaries {
            currentUser {
                id
                messageThreads {
                    nodes {
                        id
                        labels
                        unreadCount
                        collocutor {
                            id
                            fullName
                            firstName
                        }
                        lastMessage {
                            id
                            body
                            authorId
                        }
                    }
                }
            }
        }
        """,
    ),
    "ChatUnreadCounter": GraphQLOperation(
        "ChatUnreadCounter",
        """
        query ChatUnreadCounter {
            currentUser {
                id
                messageThreads {
                    unreadCount
                }
            }
        }
        """,
    ),
    # Learner wallet context: lifetime passed hours, currency, and the tutors
    # matched but awaiting first payment (`leads(status: PENDING_PAYMENT)`).
    # Verified live 2026-08-13.
    "ChatAndMessages": GraphQLOperation(
        "ChatAndMessages",
        """
        query ChatAndMessages($userId: Int!, $first: Int, $lastId: Int) {
            currentUser {
                id
                messageThread(collocutorId: $userId) {
                    id
                    labels
                    unreadCount(showSystemMessage: true)
                }
            }
            chat(userId: $userId) {
                id
                lastTutorSeenId
                lastClientSeenId
                tutoring {
                    id
                }
                collocutorUser {
                    id
                    firstName
                    profile {
                        id
                        timezone {
                            id
                            tzname
                        }
                    }
                }
                lead {
                    id
                    status
                    subject {
                        id
                        alias
                        translatedName
                    }
                }
                messages(first: $first, lastId: $lastId, showSystemMessage: true) {
                    hasNext
                    hasNewer
                    hasOlder
                    nodes {
                        id
                        body
                        threadId
                        timePosted
                        timeEdited
                        authorId
                        unread
                        isRemoved
                        isHomework
                        language
                        systemMessageType
                        appreciationSystemMessageType
                        button {
                            text
                            type
                            url
                        }
                        files {
                            id
                            name
                            url
                            downloadUrl
                            previewUrl
                            mimeType
                            size
                        }
                    }
                }
            }
        }
        """,
    ),
    # Preply's own settings-page tutoring list. It is the only verified source
    # of the *money* side of a subscription: BalanceManagementData reports refill
    # hours and dates but never `chargeAmount` or a currency, so it structurally
    # cannot answer "how much will I be charged next".
    # `$orderBy: TutoringSortInput` is nullable and the input shape was never
    # recovered from the bundles, so it is deliberately never sent.
    "LessonInsights": GraphQLOperation(
        "LessonInsights",
        """
        query LessonInsights($lessonId: Int!) {
            lessonInsights(lessonId: $lessonId) {
                generalInsights {
                    headline
                }
                transcriptConsent
            }
        }
        """,
    ),
}
