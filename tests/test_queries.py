import unittest

from preply_cli.queries import GraphQLOperation, operation_names


class QueryTests(unittest.TestCase):
    def test_core_operations_are_named_for_preply_operation_routes(self):
        names = operation_names()

        self.assertIn("TutorWallet", names)
        self.assertIn("PreplyCliStudentList", names)
        self.assertIn("TutorHomeUpcomingLessons", names)
        self.assertIn("ChatThreadSummaries", names)
        self.assertIn("PreplyCliAccountIdentity", names)
        self.assertIn("historyWithBilling", names)
        self.assertIn("history", names)
        self.assertIn("NextLessonForConfirmation", names)
        self.assertIn("ConfirmPastLesson", names)

    def test_operation_endpoint_uses_operation_name(self):
        op = GraphQLOperation("TutorWallet", "query TutorWallet { currentUser { id } }")

        self.assertEqual(op.endpoint, "/graphql/v2/TutorWallet")


if __name__ == "__main__":
    unittest.main()


class QueryPackageLayout(unittest.TestCase):
    """The split into learner/tutor/shared must not lose or shadow a document."""

    def test_every_group_is_disjoint_and_fully_merged(self):
        from preply_cli.queries import OPERATIONS
        from preply_cli.queries.learner import OPERATIONS as learner
        from preply_cli.queries.shared import OPERATIONS as shared
        from preply_cli.queries.tutor import OPERATIONS as tutor

        groups = [shared, tutor, learner]
        total = sum(len(g) for g in groups)
        self.assertEqual(total, len(OPERATIONS), "a name is defined in two groups and got shadowed")
        for group in groups:
            for name, operation in group.items():
                self.assertIs(operation, OPERATIONS[name])

    def test_each_operation_document_declares_its_own_name(self):
        # A copy-paste into the wrong group is harmless; a document whose text
        # declares a different operation name is not -- Preply routes on the URL
        # and validates on the body, so the two must agree.
        from preply_cli.queries import OPERATIONS

        for name, operation in OPERATIONS.items():
            self.assertIn(name, operation.query, f"{name} document does not mention its own name")
            self.assertEqual(f"/graphql/v2/{name}", operation.endpoint)
