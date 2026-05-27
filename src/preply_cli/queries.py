from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphQLOperation:
    name: str
    query: str

    @property
    def endpoint(self) -> str:
        return f"/graphql/v2/{self.name}"


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
    "TutorWallet": GraphQLOperation(
        "TutorWallet",
        """
        query TutorWallet {
            currentUser {
                id
                tutor {
                    id
                    lastPayoutMethod
                }
                profile {
                    id
                    currency {
                        id
                        code
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
    "PreplyCliStudentList": GraphQLOperation(
        "PreplyCliStudentList",
        """
        query PreplyCliStudentList($offset: Int!, $count: Int!, $smartFilter: TutoringSmartFilter) {
            currentUser {
                id
                firstName
                fullName
                tutor {
                    id
                    tutorings {
                        totalCount
                    }
                    studentManagementTutorings(offset: $offset, count: $count, smartFilter: $smartFilter) {
                        totalCount
                        nodes {
                            id
                            clientName
                            status
                            hours
                            totalPrepaidHours
                            totalTutorRevenue
                            confirmedLessonsCount
                            pricePerHourUsd
                            price {
                                value
                                currency {
                                    id
                                    code
                                    factor
                                    symbol
                                }
                            }
                            refill(skipStopped: false) {
                                id
                                status
                                billingFrequency
                                refillFrequency
                                refillHours
                                nextSubscription
                                nextRefill
                                lastStartingCycleDate
                            }
                            client {
                                id
                                isEnterprise
                                isB2bHourSubscriptionClient
                                user {
                                    id
                                    firstName
                                    fullName
                                    profile {
                                        id
                                        avatarUrlHttps
                                        timezone {
                                            id
                                            tzname
                                        }
                                    }
                                }
                            }
                            lead {
                                id
                                subject {
                                    id
                                    alias
                                    group
                                    translatedName
                                }
                            }
                        }
                    }
                }
            }
        }
        """,
    ),
    "TutorHomeUpcomingLessons": GraphQLOperation(
        "TutorHomeUpcomingLessons",
        """
        query TutorHomeUpcomingLessons($dateStart: Date!, $dateEnd: Date!, $tzname: String!) {
            currentUser {
                id
                tutor {
                    id
                    calendar(dateStart: $dateStart, dateEnd: $dateEnd, tzname: $tzname) {
                        nodes {
                            ... on LessonTimeslot {
                                dateStart
                                dateEnd
                                durationHours
                                lesson {
                                    id
                                    duration
                                    created
                                    isFirstLesson
                                    isLastInCycle
                                    hasBioBreak
                                    status
                                    tutor {
                                        id
                                    }
                                    client {
                                        id
                                        isB2bHourSubscriptionClient
                                        user {
                                            id
                                            fullName
                                            firstName
                                            profile {
                                                id
                                                avatarUrlHttps
                                            }
                                        }
                                    }
                                    tutoring {
                                        id
                                        clientName
                                        refill {
                                            id
                                            nextSubscription
                                            subscriptionCycles
                                        }
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
    "TutorStudentDetails": GraphQLOperation(
        "TutorStudentDetails",
        """
        query TutorStudentDetails($tutoringId: Int!) {
            tutoring(id: $tutoringId) {
                id
                clientName
                status
                activeTrialLesson {
                    id
                    created
                    status
                }
                tutor {
                    id
                }
                client {
                    id
                    user {
                        id
                        profile {
                            id
                            timezone {
                                id
                                tzname
                            }
                        }
                    }
                }
                lead {
                    id
                    subject {
                        id
                        alias
                    }
                }
            }
        }
        """,
    ),
    "TutoringStatistics": GraphQLOperation(
        "TutoringStatistics",
        """
        query TutoringStatistics($tutoringId: Int!, $cyclesCount: Int!) {
            tutoring(id: $tutoringId) {
                id
                totalTutorRevenue
                lessonsCount: confirmedLessonsCount
                monthSinceStart
                status
                hours
                totalPrepaidHours
                b2bPriceLock {
                    unlockDate
                }
                balanceUtilisation {
                    totalHours
                    utilisedHours
                }
                price {
                    value
                    currency {
                        id
                        code
                        factor
                    }
                }
                priceChangesNumber
                lessons(statuses: [BOOKED, SCHEDULED_PAST, COMPLETED, AUTOCOMPLETED], limit: 1) {
                    nodes {
                        id
                        datetime
                        isTrial
                    }
                }
                refill(skipStopped: false) {
                    id
                    status
                    billingFrequency
                    refillFrequency
                    nextSubscription
                    nextRefill
                    refillHours
                }
                recentCyclesUtilisationPercent(cycles: $cyclesCount)
            }
        }
        """,
    ),
    "TutorStudentUpcomingLessons": GraphQLOperation(
        "TutorStudentUpcomingLessons",
        """
        query TutorStudentUpcomingLessons($tutoringId: Int!) {
            tutoring(id: $tutoringId) {
                id
                client {
                    id
                    isInBioBreakExp
                    user {
                        id
                    }
                }
                tutor {
                    id
                    recurrentLessons(tutoringId: $tutoringId) {
                        id
                        nearestLessonId
                        duration
                        nearestDate
                        status
                    }
                }
                upcomingLessons(includeCompleted: true) {
                    nodes {
                        __typename
                        ... on LessonNode {
                            id
                            status
                            hasBioBreak
                            datetime
                            duration
                            earnedAmount
                            autoConfirmationInfo {
                                expectedDatetime
                            }
                            isFirstLesson
                        }
                    }
                }
            }
        }
        """,
    ),
    "TutorStudentsPastLessons": GraphQLOperation(
        "TutorStudentsPastLessons",
        """
        query TutorStudentsPastLessons(
            $tutoringId: Int!
            $offset: Int
            $limit: Int
            $status: PastLessonsFilterStatusesEnum
        ) {
            tutoring(id: $tutoringId) {
                id
                client {
                    id
                    isInBioBreakExp
                    user {
                        id
                    }
                }
                lead {
                    id
                    subject {
                        id
                        alias
                    }
                }
                pastLessons(offset: $offset, limit: $limit, includeAll: true, status: $status) {
                    nodes {
                        id
                        datetime
                        duration
                        status
                        hasIssue
                        isFirstLesson
                        canCancel
                        canChargeStudent
                        bookingType
                        hasBioBreak
                        earnedAmount
                        recurrentLessonConfig {
                            id
                            status
                        }
                        autoConfirmation
                        autoConfirmationInfo {
                            expectedDatetime
                        }
                    }
                    hasNext
                }
            }
        }
        """,
    ),
    "StudentManagementRevenueHistory": GraphQLOperation(
        "StudentManagementRevenueHistory",
        """
        query StudentManagementRevenueHistory($tutoringId: Int!) {
            tutoring(id: $tutoringId) {
                id
                price {
                    value
                    currency {
                        id
                        code
                        factor
                        symbol
                    }
                }
                tutor {
                    id
                    price {
                        value
                        currency {
                            id
                            code
                            factor
                            symbol
                        }
                    }
                }
                revenueHistory {
                    datetime
                    type
                    metadata {
                        __typename
                        ... on PriceChangeRequestEventMetadata {
                            priceChangeRequest {
                                id
                                status
                                oldPrice
                                newPrice
                            }
                        }
                        ... on SubscriptionChangeEventMetadata {
                            frequency
                            hours
                        }
                        ... on SubscriptionStartEventMetadata {
                            frequency
                            hours
                            pricePerHourUsd
                        }
                        ... on PackageEventMetadata {
                            hours
                            pricePerHourUsd
                        }
                        ... on TrialEventMetadata {
                            pricePerHourUsd
                        }
                        ... on TopUpEventMetadata {
                            hours
                        }
                    }
                }
            }
        }
        """,
    ),
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
}


def get_operation(name: str) -> GraphQLOperation:
    return OPERATIONS[name]


def operation_names() -> list[str]:
    return sorted(OPERATIONS)
