-- Триггер для уведомлений при изменении документа
CREATE OR REPLACE FUNCTION notify_document_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        INSERT INTO notifications (document_id, changed_by_employee_id, change_description)
        VALUES (
            NEW.document_id,
            current_setting('app.current_user_id')::INT,
            format('Документ "%s" был изменен сотрудником %s', NEW.title, current_setting('app.current_user_name'))
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_document_change_notification
    AFTER UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION notify_document_change();