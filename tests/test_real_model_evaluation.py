from scripts.run_real_model_evaluation import supervisor_evidence_packet


def test_supervisor_evidence_packet_filters_tenants_and_oracle_annotations():
    case = {
        "observations": [
            {
                "access_scope": "allowed",
                "evidence_id": "E1",
                "source": "log",
                "content": "disk full",
                "supports_root_cause_ids": ["disk_full"],
                "tenant_id": "tenant-a",
            },
            {
                "access_scope": "prohibited_decoy",
                "evidence_id": "E99",
                "source": "knowledge",
                "content": "foreign tenant secret",
                "supports_root_cause_ids": [],
                "tenant_id": "tenant-b",
            },
        ]
    }

    assert supervisor_evidence_packet(case) == [
        {"evidence_id": "E1", "source": "log", "content": "disk full"}
    ]
