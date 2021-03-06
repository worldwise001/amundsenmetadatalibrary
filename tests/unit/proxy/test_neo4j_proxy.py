import copy
import textwrap
import unittest
from typing import Any, Dict  # noqa: F401

from mock import patch, MagicMock
from neo4j.v1 import GraphDatabase

from metadata_service import create_app
from metadata_service.entity.popular_table import PopularTable
from metadata_service.entity.table_detail import (Application, Column, Table, Tag,
                                                  Watermark, Source, Statistics, User)
from metadata_service.entity.tag_detail import TagDetail
from metadata_service.exception import NotFoundException
from metadata_service.proxy.neo4j_proxy import Neo4jProxy
from metadata_service.util import UserResourceRel


class TestNeo4jProxy(unittest.TestCase):

    def setUp(self) -> None:
        self.app = create_app(config_module_class='metadata_service.config.LocalConfig')
        self.app_context = self.app.app_context()
        self.app_context.push()

        table_entry = {'db': {'name': 'hive'},
                       'clstr': {
                           'name': 'gold'},
                       'schema': {
                           'name': 'foo_schema'},
                       'tbl': {
                           'name': 'foo_table'},
                       'tbl_dscrpt': {
                           'description': 'foo description'}
                       }

        col1 = copy.deepcopy(table_entry)  # type: Dict[Any, Any]
        col1['col'] = {'name': 'bar_id_1',
                       'type': 'varchar',
                       'sort_order': 0}
        col1['col_dscrpt'] = {'description': 'bar col description'}
        col1['col_stats'] = [{'stat_name': 'avg', 'start_epoch': 1, 'end_epoch': 1, 'stat_val': '1'}]

        col2 = copy.deepcopy(table_entry)  # type: Dict[Any, Any]
        col2['col'] = {'name': 'bar_id_2',
                       'type': 'bigint',
                       'sort_order': 1}
        col2['col_dscrpt'] = {'description': 'bar col2 description'}
        col2['col_stats'] = [{'stat_name': 'avg', 'start_epoch': 2, 'end_epoch': 2, 'stat_val': '2'}]

        table_level_results = MagicMock()
        table_level_results.single.return_value = {
            'wmk_records': [
                {
                    'key': 'hive://gold.test_schema/test_table/high_watermark/',
                    'partition_key': 'ds',
                    'partition_value': 'fake_value',
                    'create_time': 'fake_time',
                },
                {
                    'key': 'hive://gold.test_schema/test_table/low_watermark/',
                    'partition_key': 'ds',
                    'partition_value': 'fake_value',
                    'create_time': 'fake_time',
                }
            ],
            'application': {
                'application_url': 'airflow_host/admin/airflow/tree?dag_id=test_table',
                'description': 'DAG generating a table',
                'name': 'Airflow',
                'id': 'dag/task_id'
            },
            'last_updated_timestamp': 1,
            'owner_records': [
                {
                    'key': 'tester@lyft.com',
                    'email': 'tester@lyft.com'
                }
            ],
            'tag_records': [
                {
                    'key': 'test',
                    'tag_type': 'default'
                }
            ],
            'src': {
                'source': '/source_file_loc',
                'key': 'some key',
                'source_type': 'github'
            }
        }

        table_writer = {
            'application_url': 'airflow_host/admin/airflow/tree?dag_id=test_table',
            'description': 'DAG generating a table',
            'name': 'Airflow',
            'id': 'dag/task_id'
        }

        last_updated_timestamp = '01'

        self.col_usage_return_value = [
            col1,
            col2
        ]
        self.table_level_return_value = table_level_results

        self.table_writer = table_writer

        self.last_updated_timestamp = last_updated_timestamp

    def tearDown(self) -> None:
        pass

    def test_get_table(self) -> None:
        with patch.object(GraphDatabase, 'driver'), patch.object(Neo4jProxy, '_execute_cypher_query') as mock_execute:
            mock_execute.side_effect = [self.col_usage_return_value, [], self.table_level_return_value]

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            table = neo4j_proxy.get_table(table_uri='dummy_uri')

            expected = Table(database='hive', cluster='gold', schema='foo_schema', name='foo_table',
                             tags=[Tag(tag_name='test', tag_type='default')],
                             table_readers=[], description='foo description',
                             watermarks=[Watermark(watermark_type='high_watermark',
                                                   partition_key='ds',
                                                   partition_value='fake_value',
                                                   create_time='fake_time'),
                                         Watermark(watermark_type='low_watermark',
                                                   partition_key='ds',
                                                   partition_value='fake_value',
                                                   create_time='fake_time')],
                             columns=[Column(name='bar_id_1', description='bar col description', col_type='varchar',
                                             sort_order=0, stats=[Statistics(start_epoch=1,
                                                                             end_epoch=1,
                                                                             stat_type='avg',
                                                                             stat_val='1')]),
                                      Column(name='bar_id_2', description='bar col2 description', col_type='bigint',
                                             sort_order=1, stats=[Statistics(start_epoch=2,
                                                                             end_epoch=2,
                                                                             stat_type='avg',
                                                                             stat_val='2')])],
                             owners=[User(email='tester@lyft.com')],
                             table_writer=Application(application_url=self.table_writer['application_url'],
                                                      description=self.table_writer['description'],
                                                      name=self.table_writer['name'],
                                                      id=self.table_writer['id']),
                             last_updated_timestamp=1,
                             source=Source(source='/source_file_loc',
                                           source_type='github'),
                             is_view=False)

            self.assertEqual(str(expected), str(table))

    def test_get_table_view_only(self) -> None:
        col_usage_return_value = copy.deepcopy(self.col_usage_return_value)
        for col in col_usage_return_value:
            col['tbl']['is_view'] = True

        with patch.object(GraphDatabase, 'driver'), patch.object(Neo4jProxy, '_execute_cypher_query') as mock_execute:
            mock_execute.side_effect = [col_usage_return_value, [], self.table_level_return_value]

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            table = neo4j_proxy.get_table(table_uri='dummy_uri')

            expected = Table(database='hive', cluster='gold', schema='foo_schema', name='foo_table',
                             tags=[Tag(tag_name='test', tag_type='default')],
                             table_readers=[], description='foo description',
                             watermarks=[Watermark(watermark_type='high_watermark',
                                                   partition_key='ds',
                                                   partition_value='fake_value',
                                                   create_time='fake_time'),
                                         Watermark(watermark_type='low_watermark',
                                                   partition_key='ds',
                                                   partition_value='fake_value',
                                                   create_time='fake_time')],
                             columns=[Column(name='bar_id_1', description='bar col description', col_type='varchar',
                                             sort_order=0, stats=[Statistics(start_epoch=1,
                                                                             end_epoch=1,
                                                                             stat_type='avg',
                                                                             stat_val='1')]),
                                      Column(name='bar_id_2', description='bar col2 description', col_type='bigint',
                                             sort_order=1, stats=[Statistics(start_epoch=2,
                                                                             end_epoch=2,
                                                                             stat_type='avg',
                                                                             stat_val='2')])],
                             owners=[User(email='tester@lyft.com')],
                             table_writer=Application(application_url=self.table_writer['application_url'],
                                                      description=self.table_writer['description'],
                                                      name=self.table_writer['name'],
                                                      id=self.table_writer['id']),
                             last_updated_timestamp=1,
                             source=Source(source='/source_file_loc',
                                           source_type='github'),
                             is_view=True)

            self.assertEqual(str(expected), str(table))

    def test_get_table_with_valid_description(self) -> None:
        """
        Test description is returned for table
        :return:
        """
        with patch.object(GraphDatabase, 'driver'), patch.object(Neo4jProxy, '_execute_cypher_query') as mock_execute:
            mock_execute.return_value.single.return_value = dict(description='sample description')

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            table_description = neo4j_proxy.get_table_description(table_uri='test_table')

            table_description_query = textwrap.dedent("""
            MATCH (tbl:Table {key: $tbl_key})-[:DESCRIPTION]->(d:Description)
            RETURN d.description AS description;
            """)
            mock_execute.assert_called_with(statement=table_description_query,
                                            param_dict={'tbl_key': 'test_table'})

            self.assertEquals(table_description, 'sample description')

    def test_get_table_with_no_description(self) -> None:
        """
        Test None is returned for table with no description
        :return:
        """
        with patch.object(GraphDatabase, 'driver'), patch.object(Neo4jProxy, '_execute_cypher_query') as mock_execute:
            mock_execute.return_value.single.return_value = None

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            table_description = neo4j_proxy.get_table_description(table_uri='test_table')

            table_description_query = textwrap.dedent("""
            MATCH (tbl:Table {key: $tbl_key})-[:DESCRIPTION]->(d:Description)
            RETURN d.description AS description;
            """)
            mock_execute.assert_called_with(statement=table_description_query,
                                            param_dict={'tbl_key': 'test_table'})

            self.assertIsNone(table_description)

    def test_put_table_description(self) -> None:
        """
        Test updating table description
        :return:
        """
        with patch.object(GraphDatabase, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.return_value.session.return_value = mock_session

            mock_transaction = MagicMock()
            mock_session.begin_transaction.return_value = mock_transaction

            mock_run = MagicMock()
            mock_transaction.run = mock_run
            mock_commit = MagicMock()
            mock_transaction.commit = mock_commit

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            neo4j_proxy.put_table_description(table_uri='test_table',
                                              description='test_description')

            self.assertEquals(mock_run.call_count, 2)
            self.assertEquals(mock_commit.call_count, 1)

    def test_get_column_with_valid_description(self) -> None:
        """
        Test description is returned for column
        :return:
        """
        with patch.object(GraphDatabase, 'driver'), patch.object(Neo4jProxy, '_execute_cypher_query') as mock_execute:
            mock_execute.return_value.single.return_value = dict(description='sample description')

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            col_description = neo4j_proxy.get_column_description(table_uri='test_table',
                                                                 column_name='test_column')

            column_description_query = textwrap.dedent("""
            MATCH (tbl:Table {key: $tbl_key})-[:COLUMN]->(c:Column {name: $column_name})-[:DESCRIPTION]->(d:Description)
            RETURN d.description AS description;
            """)
            mock_execute.assert_called_with(statement=column_description_query,
                                            param_dict={'tbl_key': 'test_table',
                                                        'column_name': 'test_column'})

            self.assertEquals(col_description, 'sample description')

    def test_get_column_with_no_description(self) -> None:
        """
        Test None is returned for column with no description
        :return:
        """
        with patch.object(GraphDatabase, 'driver'), patch.object(Neo4jProxy, '_execute_cypher_query') as mock_execute:
            mock_execute.return_value.single.return_value = None

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            col_description = neo4j_proxy.get_column_description(table_uri='test_table',
                                                                 column_name='test_column')

            column_description_query = textwrap.dedent("""
            MATCH (tbl:Table {key: $tbl_key})-[:COLUMN]->(c:Column {name: $column_name})-[:DESCRIPTION]->(d:Description)
            RETURN d.description AS description;
            """)
            mock_execute.assert_called_with(statement=column_description_query,
                                            param_dict={'tbl_key': 'test_table',
                                                        'column_name': 'test_column'})

            self.assertIsNone(col_description)

    def test_put_column_description(self) -> None:
        """
        Test updating column description
        :return:
        """
        with patch.object(GraphDatabase, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.return_value.session.return_value = mock_session

            mock_transaction = MagicMock()
            mock_session.begin_transaction.return_value = mock_transaction

            mock_run = MagicMock()
            mock_transaction.run = mock_run
            mock_commit = MagicMock()
            mock_transaction.commit = mock_commit

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            neo4j_proxy.put_column_description(table_uri='test_table',
                                               column_name='test_column',
                                               description='test_description')

            self.assertEquals(mock_run.call_count, 2)
            self.assertEquals(mock_commit.call_count, 1)

    def test_add_owner(self) -> None:
        with patch.object(GraphDatabase, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.return_value.session.return_value = mock_session

            mock_transaction = MagicMock()
            mock_session.begin_transaction.return_value = mock_transaction

            mock_run = MagicMock()
            mock_transaction.run = mock_run
            mock_commit = MagicMock()
            mock_transaction.commit = mock_commit

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            neo4j_proxy.add_owner(table_uri='dummy_uri',
                                  owner='tester')
            # we call neo4j twice in add_owner call
            self.assertEquals(mock_run.call_count, 2)
            self.assertEquals(mock_commit.call_count, 1)

    def test_delete_owner(self) -> None:
        with patch.object(GraphDatabase, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.return_value.session.return_value = mock_session

            mock_transaction = MagicMock()
            mock_session.begin_transaction.return_value = mock_transaction

            mock_run = MagicMock()
            mock_transaction.run = mock_run
            mock_commit = MagicMock()
            mock_transaction.commit = mock_commit

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            neo4j_proxy.delete_owner(table_uri='dummy_uri',
                                     owner='tester')
            # we only call neo4j once in delete_owner call
            self.assertEquals(mock_run.call_count, 1)
            self.assertEquals(mock_commit.call_count, 1)

    def test_add_tag(self) -> None:
        with patch.object(GraphDatabase, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.return_value.session.return_value = mock_session

            mock_transaction = MagicMock()
            mock_session.begin_transaction.return_value = mock_transaction

            mock_run = MagicMock()
            mock_transaction.run = mock_run
            mock_commit = MagicMock()
            mock_transaction.commit = mock_commit

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            neo4j_proxy.add_tag(table_uri='dummy_uri',
                                tag='hive')
            # we call neo4j twice in add_tag call
            self.assertEquals(mock_run.call_count, 3)
            self.assertEquals(mock_commit.call_count, 1)

    def test_delete_tag(self) -> None:
        with patch.object(GraphDatabase, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.return_value.session.return_value = mock_session

            mock_transaction = MagicMock()
            mock_session.begin_transaction.return_value = mock_transaction

            mock_run = MagicMock()
            mock_transaction.run = mock_run
            mock_commit = MagicMock()
            mock_transaction.commit = mock_commit

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            neo4j_proxy.delete_tag(table_uri='dummy_uri',
                                   tag='hive')
            # we only call neo4j once in delete_tag call
            self.assertEquals(mock_run.call_count, 1)
            self.assertEquals(mock_commit.call_count, 1)

    def test_get_tags(self) -> None:
        with patch.object(GraphDatabase, 'driver'), patch.object(Neo4jProxy, '_execute_cypher_query') as mock_execute:

            mock_execute.return_value = [
                {'tag_name': {'key': 'tag1'}, 'tag_count': 2},
                {'tag_name': {'key': 'tag2'}, 'tag_count': 1}
            ]

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            actual = neo4j_proxy.get_tags()

            expected = [
                TagDetail(tag_name='tag1', tag_count=2),
                TagDetail(tag_name='tag2', tag_count=1),
            ]

            self.assertEqual(actual.__repr__(), expected.__repr__())

    def test_get_neo4j_latest_updated_ts(self) -> None:
        with patch.object(GraphDatabase, 'driver'), patch.object(Neo4jProxy, '_execute_cypher_query') as mock_execute:
            mock_execute.return_value.single.return_value = {
                'ts': {
                    'latest_timestmap': '1000'
                }
            }
            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            neo4j_last_updated_ts = neo4j_proxy.get_latest_updated_ts()
            self.assertEquals(neo4j_last_updated_ts, '1000')

            mock_execute.return_value.single.return_value = {
                'ts': {

                }
            }
            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            neo4j_last_updated_ts = neo4j_proxy.get_latest_updated_ts()
            self.assertEqual(neo4j_last_updated_ts, 0)

            mock_execute.return_value.single.return_value = None
            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            neo4j_last_updated_ts = neo4j_proxy.get_latest_updated_ts()
            self.assertIsNone(neo4j_last_updated_ts)

    def test_get_popular_tables(self) -> None:
        # Test cache hit
        with patch.object(GraphDatabase, 'driver'), patch.object(Neo4jProxy, '_execute_cypher_query') as mock_execute:
            mock_execute.return_value = [{'table_key': 'foo'}, {'table_key': 'bar'}]

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            self.assertEqual(neo4j_proxy._get_popular_tables_uris(2), ['foo', 'bar'])
            self.assertEqual(neo4j_proxy._get_popular_tables_uris(2), ['foo', 'bar'])
            self.assertEqual(neo4j_proxy._get_popular_tables_uris(2), ['foo', 'bar'])

            self.assertEquals(mock_execute.call_count, 1)

        with patch.object(GraphDatabase, 'driver'), patch.object(Neo4jProxy, '_execute_cypher_query') as mock_execute:
            mock_execute.return_value = [
                {'database_name': 'db', 'cluster_name': 'clstr', 'schema_name': 'sch', 'table_name': 'foo',
                 'table_description': 'test description'},
                {'database_name': 'db', 'cluster_name': 'clstr', 'schema_name': 'sch', 'table_name': 'bar'}
            ]

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            actual = neo4j_proxy.get_popular_tables(num_entries=2)

            expected = [
                PopularTable(database='db', cluster='clstr', schema='sch', name='foo', description='test description'),
                PopularTable(database='db', cluster='clstr', schema='sch', name='bar'),
            ]

            self.assertEqual(actual.__repr__(), expected.__repr__())

    def test_get_users(self) -> None:
        with patch.object(GraphDatabase, 'driver'), patch.object(Neo4jProxy, '_execute_cypher_query') as mock_execute:
            mock_execute.return_value.single.return_value = {
                'user_record': {
                    'employee_type': 'teamMember',
                    'full_name': 'test_full_name',
                    'is_active': 'True',
                    'github_username': 'test-github',
                    'slack_id': 'test_id',
                    'last_name': 'test_last_name',
                    'first_name': 'test_first_name',
                    'team_name': 'test_team',
                    'email': 'test_email',
                },
                'manager_record': {
                    'full_name': 'test_manager_fullname'
                }
            }
            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            neo4j_user = neo4j_proxy.get_user_detail(user_id='test_email')
            self.assertEquals(neo4j_user.email, 'test_email')

    def test_get_resources_by_user_relation(self) -> None:
        with patch.object(GraphDatabase, 'driver'), patch.object(Neo4jProxy, '_execute_cypher_query') as mock_execute:

            mock_execute.return_value = [
                {
                    'tbl': {
                        'name': 'table_name'
                    },
                    'db': {
                        'name': 'db_name'
                    },
                    'clstr': {
                        'name': 'cluster'
                    },
                    'schema': {
                        'name': 'schema'
                    },
                }
            ]

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            result = neo4j_proxy.get_table_by_user_relation(user_email='test_user',
                                                            relation_type=UserResourceRel.follow)
            self.assertEqual(len(result['table']), 1)
            self.assertEqual(result['table'][0].name, 'table_name')
            self.assertEqual(result['table'][0].database, 'db_name')
            self.assertEqual(result['table'][0].cluster, 'cluster')
            self.assertEqual(result['table'][0].schema, 'schema')

    def test_add_resource_relation_by_user(self) -> None:
        with patch.object(GraphDatabase, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.return_value.session.return_value = mock_session

            mock_transaction = MagicMock()
            mock_session.begin_transaction.return_value = mock_transaction

            mock_run = MagicMock()
            mock_transaction.run = mock_run
            mock_commit = MagicMock()
            mock_transaction.commit = mock_commit

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            neo4j_proxy.add_table_relation_by_user(table_uri='dummy_uri',
                                                   user_email='tester',
                                                   relation_type=UserResourceRel.follow)
            self.assertEquals(mock_run.call_count, 2)
            self.assertEquals(mock_commit.call_count, 1)

    def test_delete_resource_relation_by_user(self) -> None:
        with patch.object(GraphDatabase, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.return_value.session.return_value = mock_session

            mock_transaction = MagicMock()
            mock_session.begin_transaction.return_value = mock_transaction

            mock_run = MagicMock()
            mock_transaction.run = mock_run
            mock_commit = MagicMock()
            mock_transaction.commit = mock_commit

            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            neo4j_proxy.delete_table_relation_by_user(table_uri='dummy_uri',
                                                      user_email='tester',
                                                      relation_type=UserResourceRel.follow)
            self.assertEquals(mock_run.call_count, 1)
            self.assertEquals(mock_commit.call_count, 1)

    def test_get_invalid_user(self) -> None:
        with patch.object(GraphDatabase, 'driver'), patch.object(Neo4jProxy, '_execute_cypher_query') as mock_execute:
            mock_execute.return_value.single.return_value = None
            neo4j_proxy = Neo4jProxy(host='DOES_NOT_MATTER', port=0000)
            self.assertRaises(NotFoundException, neo4j_proxy.get_user_detail, user_id='invalid_email')


if __name__ == '__main__':
    unittest.main()
