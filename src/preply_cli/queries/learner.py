"""Learner-side operations, each verified against a live learner account."""

from __future__ import annotations

from ._operation import GraphQLOperation

OPERATIONS: dict[str, GraphQLOperation] = {
    "NextLessonForConfirmation": GraphQLOperation(
        "NextLessonForConfirmation",
        """
        query NextLessonForConfirmation {
            currentUser {
                id
                firstName
                client {
                    id
                    isEnterprise
                }
                profile {
                    id
                    countryCode
                    language {
                        code
                    }
                }
            }
            myNextLessonForConfirmation {
                id
                datetime
                status
                isFirstLesson
                tutor {
                    id
                    user {
                        id
                        firstName
                        profile {
                            id
                            avatar {
                                url
                            }
                        }
                    }
                }
                tutoring {
                    id
                    lead {
                        id
                        subject {
                            id
                            alias
                        }
                    }
                }
            }
        }
        """,
    ),
    "ConfirmPastLesson": GraphQLOperation(
        "ConfirmPastLesson",
        """
        mutation ConfirmPastLesson($lessonId: Int!) {
            confirmLesson(lessonId: $lessonId) {
                ok
                lesson {
                    id
                    hasIssue
                    status
                }
            }
        }
        """,
    ),
    "historyWithBilling": GraphQLOperation(
        "historyWithBilling",
        """
        query historyWithBilling {
            paymentsHistory {
                payments {
                    id
                    subject
                    tutor
                    time
                    hours
                    amount
                    currencyCode
                    currencySymbol
                    receiptUrl
                    studentCanRefund
                }
                hasNext
            }
            currentUser {
                id
                fullName
                tutor {
                    id
                }
                profile {
                    id
                    billingInformation {
                        receiverName
                        company
                        vatNumber
                        addressLine1
                        addressLine2
                        addressLine3
                    }
                }
            }
        }
        """,
    ),
    "history": GraphQLOperation(
        "history",
        """
        query history($lastId: Int) {
            paymentsHistory(lastId: $lastId) {
                payments {
                    id
                    subject
                    tutor
                    time
                    hours
                    amount
                    currencyCode
                    currencySymbol
                    receiptUrl
                    studentCanRefund
                }
                hasNext
            }
        }
        """,
    ),
    # Learner-side completed-lesson event ledger. Unlike `history`
    # (a billing surface), each node here is one actual lesson with its
    # datetime, status, duration, paid amount, and rating. Recovered from
    # Preply's public bundles and verified live on a learner account
    # 2026-08-13. This is the learner lesson ledger the older notes said
    # was not exposed.
    "CurrentUserPastLessons": GraphQLOperation(
        "CurrentUserPastLessons",
        """
        query CurrentUserPastLessons($offset: Int!, $limit: Int!, $excludeUnconfirmedLessons: Boolean) {
            currentUser {
                id
                client {
                    id
                    pastLessons(
                        limit: $limit
                        offset: $offset
                        excludeUnconfirmedLessons: $excludeUnconfirmedLessons
                    ) {
                        hasNext
                        nodes {
                            id
                            datetime
                            duration
                            status
                            paidAmount
                            isEligibleForReporting
                            isRated
                            isFirstLesson
                            hasBioBreak
                            tutor {
                                id
                                user {
                                    id
                                    firstName
                                    profile {
                                        id
                                        avatarUrlHttps
                                    }
                                }
                            }
                            tutoring {
                                id
                                hours
                                lead {
                                    id
                                    subject {
                                        id
                                        translatedName
                                    }
                                }
                            }
                            recurrentLessonConfig {
                                id
                            }
                            rating {
                                id
                                amount
                            }
                        }
                    }
                }
            }
        }
        """,
    ),
    # Learner upcoming lessons (union of booked lessons and recurrent
    # reservations). Verified live on a learner account 2026-08-13.
    "CurrentUserUpcomingLessons": GraphQLOperation(
        "CurrentUserUpcomingLessons",
        """
        query CurrentUserUpcomingLessons {
            currentUser {
                id
                client {
                    id
                    upcomingLessons {
                        nodes {
                            __typename
                            ... on LessonNode {
                                id
                                datetime
                                duration
                                status
                                paidAmount
                                isFirstLesson
                                bookingType
                                tutor {
                                    id
                                    user { id firstName }
                                }
                                tutoring {
                                    id
                                    lead { id subject { id translatedName alias } }
                                    refill { id status nextSubscription }
                                }
                            }
                            ... on RecurrentLessonReservationNode {
                                id
                                datetime
                                duration
                                conflictReason
                                tutoring {
                                    id
                                    lead { id subject { id translatedName } }
                                    tutor { id user { id firstName } }
                                    refill { id status nextSubscription }
                                }
                            }
                        }
                    }
                }
            }
        }
        """,
    ),
    # Learner active subscriptions / tutorings: price, lessons taken, subject,
    # tutor, and refill (subscription) state. Verified live 2026-08-13.
    "UserActiveTutorings": GraphQLOperation(
        "UserActiveTutorings",
        """
        query UserActiveTutorings {
            currentUser {
                id
                client {
                    id
                    tutorings {
                        nodes {
                            id
                            pricePerHourUsd
                            canUpgrade
                            canTopUp
                            created
                            confirmedLessonsCount
                            tutor {
                                id
                                user { id firstName }
                            }
                            lead {
                                id
                                subject { id alias translatedName }
                            }
                            refill(skipStopped: true) {
                                id
                                status
                                type
                                refillHours
                                canPostponeSubscription
                            }
                        }
                    }
                }
            }
        }
        """,
    ),
    # Learner lifetime learning stats: streak, lessons completed, practices.
    # Verified live 2026-08-13.
    "ClientLifetimeStats": GraphQLOperation(
        "ClientLifetimeStats",
        """
        query ClientLifetimeStats {
            currentUser {
                id
                client {
                    id
                    learningActivities {
                        id
                        lifetimeStats {
                            id
                            highestLessonStreak
                            lessonsCompleted
                            practicesCompleted
                        }
                    }
                }
            }
        }
        """,
    ),
    # Learner hour balance and refill (subscription) schedule. This is the only
    # operation that reports `totalBalance` plus, per tutoring, how many paid
    # hours are still unscheduled and when the next automatic charge lands.
    # `refill` is null for tutorings whose subscription was stopped, so those
    # hours sit banked with no upcoming charge. Verified live 2026-08-13.
    "BalanceManagementData": GraphQLOperation(
        "BalanceManagementData",
        """
        query BalanceManagementData {
            balanceManagementData {
                totalBalance
                totalNodesCount
                nodes {
                    unavailableLessons
                    unscheduledLessons
                    hoursNotInDanger
                    unscheduledLessonsFromPastCycle
                    lead {
                        id
                        subject {
                            id
                            alias
                        }
                    }
                    refill {
                        id
                        billingHours
                        lastStartingCycleDate
                        refillHours
                        nextSubscription
                        status
                        billingFrequency
                        isStoppedFromSystem
                        updated
                        nextRefill
                        retryCharges
                    }
                    tutoring {
                        id
                        isTransferEnabled
                        ratioLessonsCompletedInCycle
                        tutor {
                            id
                            currentUserBlocked
                            user {
                                id
                                firstName
                                profile {
                                    id
                                    avatar {
                                        uri
                                    }
                                }
                            }
                        }
                        priceChangeRequestStatus {
                            id
                            status
                        }
                        hours
                    }
                }
            }
        }
        """,
    ),
    # Learner subscription posture: which subscription model is in force and
    # whether the account currently counts as an active subscriber.
    # Verified live 2026-08-13.
    "UserSubscriptionsData": GraphQLOperation(
        "UserSubscriptionsData",
        """
        query UserSubscriptionsData {
            currentUser {
                id
                client {
                    id
                    subscriptionType
                    isActiveSubscriber
                }
            }
        }
        """,
    ),
    # Unread message count only - far cheaper than fetching thread summaries
    # when a dashboard just needs the badge number. Verified live 2026-08-13.
    "ClientWallet": GraphQLOperation(
        "ClientWallet",
        """
        query ClientWallet {
            currentUser {
                id
                client {
                    id
                    isEnterprise
                    passedHours
                    user {
                        id
                        fullName
                        profile {
                            id
                            currency {
                                id
                                code
                                factor
                                translatedCode
                            }
                            countryCode
                        }
                    }
                    leads(status: PENDING_PAYMENT) {
                        nodes {
                            id
                            pricePerHourUsd
                            tutor {
                                id
                                status
                                user {
                                    id
                                    fullName
                                    profile {
                                        id
                                        avatarUrl
                                        countryCode
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """,
    ),
    # Full conversation history with one collocutor. Contradicts the earlier
    # assumption that transcript export needs the Agora chat transport: message
    # bodies come back over plain GraphQL. Agora carries the *live* stream, not
    # the history. Fragments are inlined (the public bundle ships them
    # separately). `first` pages backwards from newest; `hasNext` means older
    # messages remain. Verified live 2026-08-14.
    "SettingsTutoringList": GraphQLOperation(
        "SettingsTutoringList",
        """
        query SettingsTutoringList($orderBy: TutoringSortInput) {
            currentUser {
                id
                client {
                    id
                    tutorings(offset: 0, orderBy: $orderBy) {
                        nodes {
                            id
                            hours
                            isTransferEnabled
                            totalPrepaidHours
                            paymentsCount
                            ratioLessonsCompletedInCycle
                            relevantActionsBanner {
                                primaryAction
                                secondaryAction
                            }
                            lead {
                                id
                                subject {
                                    id
                                    translatedName
                                }
                            }
                            refill(skipStopped: false) {
                                id
                                hours
                                chargeAmount
                                nextSubscription
                                type
                                status
                                currency {
                                    id
                                    code
                                }
                                refillFrequency
                                refillHours
                                billingFrequency
                                canPostponeSubscription
                                isStoppedFromSystem
                                nextRefill
                                billingHours
                                retryCharges
                            }
                            tutor {
                                id
                                currentUserBlocked
                                user {
                                    id
                                    fullName
                                    firstName
                                }
                            }
                            priceChangeRequestStatus {
                                id
                                status
                                subsPriceLocalized
                            }
                        }
                    }
                }
            }
        }
        """,
    ),
    "AllAchievementCertificate": GraphQLOperation(
        "AllAchievementCertificate",
        """
        query AllAchievementCertificate {
            allAchievementCertificates {
                currentLevel
                nextLevel
                hoursToNextLevel
                downloadUrl
                subject {
                    id
                    alias
                    translatedName
                }
                completedHours
            }
        }
        """,
    ),
    # Companion to ConfirmPastLesson: the mutation shipped without any way to
    # list its own inputs. `autoConfirmation` is the part that matters most --
    # it decides whether ignoring the prompt still moves money.
    "UnconfirmedLessons": GraphQLOperation(
        "UnconfirmedLessons",
        """
        query UnconfirmedLessons($offset: Int!, $limit: Int!) {
            currentUser {
                id
                client {
                    id
                    autoConfirmation
                    unconfirmedLessons(offset: $offset, limit: $limit) {
                        hasNext
                        nodes {
                            id
                            duration
                            datetime
                            status
                            isFirstLesson
                            isEligibleForReporting
                            tutor {
                                id
                                user {
                                    id
                                    fullName
                                    firstName
                                }
                            }
                            tutoring {
                                id
                                lead {
                                    id
                                    subject {
                                        id
                                        alias
                                        translatedName
                                    }
                                }
                            }
                            reportedIssues {
                                id
                                reporterType
                                reason
                                created
                            }
                        }
                    }
                }
            }
        }
        """,
    ),
}
