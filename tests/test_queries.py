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

    def test_operation_endpoint_uses_operation_name(self):
        op = GraphQLOperation("TutorWallet", "query TutorWallet { currentUser { id } }")

        self.assertEqual(op.endpoint, "/graphql/v2/TutorWallet")


if __name__ == "__main__":
    unittest.main()
